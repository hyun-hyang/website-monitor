#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import time
from datetime import datetime, timezone
from typing import Iterable, List, Dict, Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]    # src/slack → src → <repo>
from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")


def parse_time(v: Optional[str]) -> Optional[float]:
    """
    입력을 Slack epoch(float)로 변환.
    - 숫자: 그대로 epoch로 간주
    - ISO8601: 2025-08-26T04:00:00 또는 2025-08-26 04:00:00, 2025-08-26 (UTC로 처리)
    """
    if not v:
        return None
    v = v.strip()
    # 숫자(epoch)면 그대로
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return float(v)
    # ISO8601 류 파싱 (여기선 naive를 UTC로 간주)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(v, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse time: {v}")


def from_this_bot(msg: Dict[str, Any], auth_info: Dict[str, Any]) -> bool:
    """
    메시지가 '내 봇'이 보낸 것인지 판정.
    """
    bot_user_id = auth_info.get("user_id")
    app_id = auth_info.get("app_id")

    if msg.get("user") and bot_user_id and msg["user"] == bot_user_id:
        return True
    if msg.get("bot_id"):
        return True
    if msg.get("app_id") and app_id and msg["app_id"] == app_id:
        return True
    return False


def iter_messages(
    client: WebClient,
    channel: str,
    oldest: Optional[float],
    latest: Optional[float],
    max_fetch: int,
) -> Iterable[Dict[str, Any]]:
    """
    채널 내 메시지 이터레이터 (최신 → 과거).
    oldest(>=), latest(<=)는 Slack epoch(초).
    """
    cursor = None
    fetched = 0
    while True:
        try:
            resp = client.conversations_history(
                channel=channel,
                limit=min(200, max(1, max_fetch - fetched)),
                oldest=oldest,
                latest=latest,
                cursor=cursor,
                inclusive=True,
            )
        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                retry = int(e.response.headers.get("Retry-After", "5"))
                time.sleep(retry)
                continue
            raise

        msgs = resp.get("messages", [])
        for m in msgs:
            yield m
            fetched += 1
            if fetched >= max_fetch:
                return

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return


def main():
    # .env 로드 (현재 경로)
    load_dotenv()

    ap = argparse.ArgumentParser(
        description="Delete Slack messages (one-off, safe by default)"
    )
    ap.add_argument("--token",
                    default=os.getenv("SLACK_BOT_TOKEN"),
                    help="xoxb- Bot token (or set SLACK_BOT_TOKEN)")
    # .env 있으면 기본값 사용, 없으면 필수
    env_channel = os.getenv("SLACK_CHANNEL_ID")
    ap.add_argument("--channel",
                    default=env_channel,
                    required=not bool(env_channel),
                    help="Channel ID like C0123456789 (or set SLACK_CHANNEL_ID)")

    ap.add_argument("--contains", help="Delete only if text contains this literal")
    ap.add_argument("--regex", help="Delete only if text matches this regex (Python re)")
    ap.add_argument("--since", help="Oldest time (epoch or 'YYYY-MM-DD[ HH:MM:SS]')")
    ap.add_argument("--until", help="Latest time (epoch or 'YYYY-MM-DD[ HH:MM:SS]')")
    ap.add_argument("--max", type=int, default=1000, help="Max messages to scan (default: 1000)")

    # 안전 기본값: 내 봇이 보낸 메시지만 삭제. (사람/타봇은 --include-others 로 허용)
    ap.add_argument("--include-others", action="store_true",
                    help="Also allow deleting non-bot messages (danger)")
    ap.add_argument("--yes", action="store_true",
                    help="Actually delete (without this, DRY-RUN)")
    args = ap.parse_args()

    token = args.token
    if not token or not token.startswith("xoxb-"):
        ap.error("Valid Bot token required (xoxb-...). Use --token or export SLACK_BOT_TOKEN.")

    client = WebClient(token=token)

    # 토큰 검증 & 봇 정보
    auth = client.auth_test()
    print(f"[auth] ok={auth['ok']} bot_user_id={auth.get('user_id')} app_id={auth.get('app_id')}")

    oldest = parse_time(args.since)
    latest = parse_time(args.until)

    substr = args.contains
    rx = re.compile(args.regex) if args.regex else None

    bot_only = not args.include_others

    candidates: List[Dict[str, Any]] = []
    for m in iter_messages(client, args.channel, oldest, latest, max_fetch=args.max):
        text = m.get("text", "") or ""
        if substr and substr not in text:
            continue
        if rx and not rx.search(text):
            continue
        if bot_only and not from_this_bot(m, auth):
            continue
        candidates.append(m)

    if not candidates:
        print("No messages matched. (Nothing to delete)")
        return

    print(f"\nFound {len(candidates)} message(s) to delete (DRY-RUN by default):\n")
    for m in candidates:
        ts = m.get("ts")
        user = m.get("user") or "-"
        preview = (m.get("text") or "").replace("\n", " ")[:120]
        print(f"- ts={ts} user={user} text={preview!r}")

    if not args.yes:
        print("\nDRY-RUN: nothing deleted. Add --yes to actually delete.")
        return

    errors = 0
    for m in candidates:
        ts = m["ts"]
        try:
            resp = client.chat_delete(channel=args.channel, ts=ts)
            if resp.get("ok"):
                print(f"✅ deleted ts={ts}")
            else:
                print(f"❌ failed ts={ts} resp={resp}")
                errors += 1
        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                retry = int(e.response.headers.get("Retry-After", "5"))
                print(f"Rate limited. Sleeping {retry}s…")
                time.sleep(retry)
                # 재시도는 루프 다음 아이템으로 진행(원한다면 같은 ts 재시도 로직 추가 가능)
                continue
            print(f"❌ error ts={ts} -> {e.response.get('error')}")
            errors += 1

    if errors:
        print(f"\nDone with {errors} error(s).")
    else:
        print("\nDone. All selected messages deleted.")


if __name__ == "__main__":
    main()