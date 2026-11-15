# -*- coding: utf-8 -*-
"""문의 추적 수집 서버 (지시서 6장). 표준 라이브러리만 사용.

이벤트는 events.jsonl에, 문의 폼은 inquiries.jsonl에 한 줄씩 저장.
가비아 서버에서: python server.py 8899  (앞단 nginx에서 /track -> 이 포트로 프록시 + HTTPS)
"""
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_OPTIONS(self):
        self._ok()

    def do_POST(self):
        name = {"/event": "events.jsonl", "/inquiry": "inquiries.jsonl"}.get(self.path)
        if not name:
            self.send_response(404); self.end_headers(); return
        try:
            raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 10_000))
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self.send_response(400); self.end_headers(); return
        row["received"] = datetime.now().isoformat(timespec="seconds")
        with open(BASE / name, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._ok()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"추적 서버 시작: 포트 {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
