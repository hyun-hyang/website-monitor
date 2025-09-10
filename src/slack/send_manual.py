import os, requests
from dotenv import load_dotenv

load_dotenv()
webhook_url = os.getenv("SLACK_WEBHOOK_URL")

payload = {
  "text": "🔔 *일반대학원*에 새로운 공지사항!",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "📢 일반대학원 새 공지사항"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*장학*\n• <https://graduate.korea.ac.kr/community/notice_view.html?no=1256&page=1|[대학원행정팀] 대학원행정팀 근로장학생(대학원생) 모집 공고>\n   📅 2025.09.09   Views 178"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*기타*\n• <https://graduate.korea.ac.kr/community/notice_view.html?no=1254&page=1|2025-2학기 학생예비군 보류자(전입) 신고 안내>\n   📅 2025.09.08   Views 51"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "• <https://graduate.korea.ac.kr/community/notice_view.html?no=1255&page=1|[대학원행정팀, BK21] 2025학년도 3차 언어교환 프로그램 신청 안내 (~9/14)>\n   📅 2025.09.10   Views 190"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "• <https://graduate.korea.ac.kr/community/notice_view.html?no=1259&page=1|2025년 후반기 학생예비군 훈련일정 알림>\n   📅 2025.09.10   Views 40"
      }
    }
  ]
}

resp = requests.post(webhook_url, json=payload)
resp.raise_for_status()
print("Slack 전송 완료!")