# -*- coding: utf-8 -*-
"""글해줌 GitHub 앱 만들기 — 처음 한 번, 대표님 PC에서.   python -X utf8 engine/github_app.py [앱 이름]

왜: 글해줌 서버가 고객 홈페이지 저장소에 글을 넣으려면 열쇠가 필요하다. 고객마다 토큰을 만들면 수천 곳에서
'만들기·1년마다 갈기'가 끝나지 않는다. 앱 하나면 서버가 필요할 때 1시간짜리 열쇠를 스스로 받는다(만료 관리 없음).
권한은 '글 넣기(Contents 쓰기)' 하나. 설치는 '선택한 저장소'만 — 엔진(sotong-apt)·도구(corp-tool)는 넣지 않는다.
서버가 털려도 고객 글 저장소까지만이고, 모든 고객 빌드가 받아 가는 엔진은 못 건드린다.
새 고객 저장소는 설치 화면에서 대표님이 체크 한 번(deploy.py open 이 링크를 띄움 — 설치 목록 API 는 앱 사용자 토큰만 받아서, 11/20 실측).

흐름: 이 PC에 잠깐 창구(localhost:8765)를 연다 → 브라우저가 GitHub '앱 만들기' 화면으로 → 대표님 [Create] 한 번
→ GitHub 가 돌려준 일회용 코드로 앱 열쇠(pem)를 받아 ~/.sotong/ 에 저장(화면에 안 찍음) → 설치 화면 주소 안내.
"""
import html
import http.server
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

KEYS = Path.home() / ".sotong"
PORT = 8765
STATE = secrets.token_hex(8)
MANIFEST = {"name": sys.argv[1] if len(sys.argv) > 1 else "geulhaejum-publisher", "url": "https://geulhaejum.kr", "public": False,
            "hook_attributes": {"url": "https://geulhaejum.kr/", "active": False},
            "redirect_url": f"http://localhost:{PORT}/done",
            "default_permissions": {"contents": "write", "metadata": "read"}, "default_events": []}


class Desk(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if not self.path.startswith("/done"):   # 첫 화면: 설계서를 GitHub 로 바로 넘긴다
            return self.reply(f'<form id="f" method="post" action="https://github.com/settings/apps/new?state={STATE}">'
                              f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(MANIFEST))}"></form>'
                              '<p>GitHub 앱 만들기 화면으로 넘어갑니다…</p><script>document.getElementById("f").submit()</script>')
        if q.get("state", [""])[0] != STATE or "code" not in q:
            return self.reply("<p>확인값이 맞지 않습니다. 터미널에서 다시 실행해 주세요.</p>")
        req = urllib.request.Request(f"https://api.github.com/app-manifests/{q['code'][0]}/conversions", method="POST",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "sotong-apt"})
        app = json.load(urllib.request.urlopen(req, timeout=20))
        KEYS.mkdir(exist_ok=True)
        (KEYS / "github_app.pem").write_text(app["pem"], encoding="utf-8")
        (KEYS / "github_app.json").write_text(json.dumps({"id": app["id"], "slug": app["slug"], "client_id": app["client_id"]}),
                                              encoding="utf-8")
        self.reply(f"<p>앱 <b>{html.escape(app['slug'])}</b> 를 만들었습니다. 이 창을 닫고 터미널 안내를 따라 주세요.</p>")
        print(f"\n앱 만들기 끝: {app['slug']} (번호 {app['id']}) — 열쇠 {KEYS / 'github_app.pem'} (값은 화면에 안 찍음)\n"
              f"다음 한 번: https://github.com/apps/{app['slug']}/installations/new\n"
              "  → 'Only select repositories' → 고객 저장소 하나 고르고 Install (이후 고객도 deploy.py open 이 띄우는 같은 링크에서 체크 한 번)\n"
              "  → 글해줌 서버 .env 에 GITHUB_APP_ID·GITHUB_APP_KEY 를 넣는 것은 글해줌 창 몫")
        self.server.done = True

    def reply(self, body):
        data = f'<!doctype html><meta charset="utf-8"><body style="font:16px sans-serif;padding:40px">{body}'.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    if (KEYS / "github_app.json").exists():
        sys.exit(f"이미 앱이 있습니다: {KEYS / 'github_app.json'} — 새로 만들려면 그 파일과 github_app.pem 을 치우고 다시")
    srv = http.server.HTTPServer(("127.0.0.1", PORT), Desk)
    srv.done = False
    print(f"브라우저에서 GitHub 앱 만들기 화면이 열립니다 — [Create GitHub App for …] 한 번 누르시면 됩니다")
    webbrowser.open(f"http://localhost:{PORT}/")
    while not srv.done:
        srv.handle_request()
