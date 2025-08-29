#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
from typing import List
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]    # src/slack → src → <repo>
from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

def load_ts_from_file(path: str) -> List[str]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t and not t.startswith("#"):
                items.append(t)
    return items

def _extract_rich_text_elements(el):
    out = []
    t = el.get("type")
    if t == "text":
        out.append(el.get("text", ""))
    elif t == "link":
        # <url|text> 형태로
        url = el.get("url", "")
        txt = el.get("text") or url
        out.append(f"<{url}|{txt}>")
    elif t in ("user", "usergroup", "channel"):
        # 간단 표기
        out.append(f"<{t}:{el.get(t+'_id','')}>")
    elif t == "emoji":
        out.append(f":{el.get('name', '')}:")
    # 필요시 추가 타입 처리
    return "".join(out)

def _extract_from_blocks(blocks):
    lines = []
    for b in blocks or []:
        btype = b.get("type")
        if btype in ("section", "header"):
            txt = b.get("text") or {}
            if isinstance(txt, dict) and txt.get("text"):
                lines.append(txt["text"])
        if btype == "section" and b.get("fields"):
            for f in b["fields"]:
                if isinstance(f, dict) and f.get("text"):
                    lines.append(f["text"])
        if btype == "rich_text":
            # rich_text는 elements → sub-elements → elements 구조
            for blk in b.get("elements", []):
                if blk.get("type") == "rich_text_section":
                    segs = []
                    for el in blk.get("elements", []):
                        segs.append(_extract_rich_text_elements(el))
                    if segs:
                        lines.append("".join(segs))
                elif blk.get("type") == "rich_text_list":
                    items = []
                    for it in blk.get("elements", []):
                        # 리스트 항목도 section처럼 elements를 갖는다
                        segs = []
                        for el in it.get("elements", []):
                            segs.append(_extract_rich_text_elements(el))
                        if segs:
                            items.append("".join(segs))
                    if items:
                        lines.extend([f"• {x}" for x in items])
    return lines

def extract_message_text(m):
    # 1) 기본 text
    texts = []
    base = m.get("text")
    if base:
        texts.append(base)

    # 2) blocks
    texts.extend(_extract_from_blocks(m.get("blocks", [])))

    # 3) attachments(내부에 text 또는 blocks가 있을 수 있음)
    for att in m.get("attachments", []) or []:
        if att.get("text"):
            texts.append(att["text"])
        if att.get("blocks"):
            texts.extend(_extract_from_blocks(att["blocks"]))

    # 중복/공백 정리
    dedup = []
    for line in texts:
        line = (line or "").replace("\n", " ").strip()
        if line and line not in dedup:
            dedup.append(line)
    return " / ".join(dedup) if dedup else ""


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.getenv("SLACK_BOT_TOKEN"))
    ap.add_argument("--channel", default=os.getenv("SLACK_CHANNEL_ID"), required=not bool(os.getenv("SLACK_CHANNEL_ID")))
    ap.add_argument("--ts", required=True, help="e.g. 1756181407.518089")
    ap.add_argument("--yes", action="store_true", help="actually delete")
    args = ap.parse_args()

    client = WebClient(token=args.token)

    # 미리 메시지 존재/소유 확인
    try:
        auth = client.auth_test()
        auth_app = auth.get("app_id")
        hist = client.conversations_history(channel=args.channel, inclusive=True, latest=args.ts, oldest=args.ts, limit=1)
        msgs = hist.get("messages", [])
        if not msgs:
            print("Target message not found (maybe already deleted?).")
            return
        msg = msgs[0]
        print(f"Found message: ts={msg['ts']}")
        print(f"app_id={msg.get('app_id')} bot_id={msg.get('bot_id')} user={msg.get('user')}")
        print(f"text={(msg.get('text') or '')[:200]!r}")
        print(f"blocks? {bool(msg.get('blocks'))}")
        if msg.get("app_id") and auth_app and msg["app_id"] != auth_app:
            print("⚠️ Different app_id → this bot cannot delete that message.")
            return
    except SlackApiError as e:
        print("Read error:", e.response.get("error"), e.response.data)
        return

    if not args.yes:
        print("DRY-RUN (add --yes to delete).")
        return

    # 실제 삭제
    try:
        resp = client.chat_delete(channel=args.channel, ts=args.ts)
        if resp.get("ok"):
            print("✅ deleted:", args.ts)
        else:
            print("❌ delete failed:", resp.data)
    except SlackApiError as e:
        print("❌ Slack error:", e.response.get("error"))
        # 레이트리밋 대응
        if e.response.get("error") == "ratelimited":
            retry = int(e.response.headers.get("Retry-After", "5"))
            print(f"Retrying after {retry}s…")
            time.sleep(retry)
            resp = client.chat_delete(channel=args.channel, ts=args.ts)
            print("Retry result:", resp.data)

if __name__ == "__main__":
    main()