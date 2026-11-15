# -*- coding: utf-8 -*-
"""월간 리포트 생성 (지시서 6장 문장 형태 그대로).

사용법: python report.py [YYYY-MM]   (생략 시 지난달)
출력: 리포트 문자열 -> 문자/메일 발송 스크립트에 붙여서 사용.
"""
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent


def load(name, month):
    p = BASE / name
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("ts", row.get("received", "")).startswith(month):
            rows.append(row)
    return rows


def build_report(month):
    events = load("events.jsonl", month)
    inquiries = load("inquiries.jsonl", month)
    count = lambda t: sum(1 for e in events if e.get("type") == t)
    visits = [e for e in events if e.get("type") == "visit"]
    search = sum(1 for v in visits if v.get("source") == "search")
    return "\n".join([
        f"[{month}] 이번 달 홈페이지로",
        f"  전화 클릭 {count('tel')}회",
        f"  카톡 클릭 {count('kakao')}회",
        f"  문의 폼 {len(inquiries)}건",
        f"  방문 {len(visits)}회 (검색 유입 {search}회)",
    ])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        month = sys.argv[1]
    else:
        today = date.today()
        month = f"{today.year - 1}-12" if today.month == 1 else f"{today.year}-{today.month - 1:02d}"
    print(build_report(month))
    # ponytail: 발송은 수동 복붙으로 시작, 고객 5명 넘으면 기존 blog-auto 문자 발송 모듈에 크론으로 연결
