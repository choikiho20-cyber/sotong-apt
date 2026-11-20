# -*- coding: utf-8 -*-
"""법인 단지 짓고 올리기.  python -X utf8 deploy.py <세대|all>
새 고객 개통(한 번에).   python -X utf8 deploy.py open <세대> 받은값.json [도메인]   ← 대표님 터미널
처음 한 번 열쇠 준비.    python -X utf8 deploy.py setup
도구 문을 글해줌 로그인으로. python -X utf8 deploy.py login <세대> <고객 글해줌 메일>
입주 폴더만 만들기.      python -X utf8 deploy.py new <세대> 받은값.json [도메인]
세대 config.json 의 pages_project(Cloudflare Pages 이름)가 있는 세대가 법인 단지다. 자동차 단지는 cf_project·admin_repo(engine/car/apt.py).
업무 도구(법인도구/web)·엔진을 고쳤으면 all — 견본은 이 PC에서, 실고객(admin_repo)은 그 저장소 Actions 가 다시 짓는다.
실고객 세대의 원본은 비공개 저장소다(11/20 A안): 글해줌이 inbox/ 에 글을 넣으면 Actions 가 publish.py → deploy.py . 로 짓고 올린다."""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ENGINE = Path(__file__).resolve().parent
UNITS = ENGINE.parents[1] / "units"
SAMPLE = UNITS / "demo-corp"
AUDIT = Path.home() / ".claude" / "skills" / "homepage-seo" / "audit.py"   # 홈페이지 검색 점검표(FAIL 0 이어야 납품)
OWNER = "choikiho20-cyber"
TRACK_URL = "https://car-track.choikiho20.workers.dev"
# 열쇠 보관함 — 저장소 밖, 이 PC에만. 값은 화면에 찍지 않고 파일→stdin 으로만 넘긴다.
#   cloudflare_token.txt(Pages 편집) · cloudflare_account.txt · corp_tool_key(corp-tool 읽기 전용 배포 열쇠)
#   tools_api_key.txt(글해줌 로그인 문, login 때만) · github_app.json/.pem(글해줌 앱, engine/github_app.py 가 만듦)
KEYS = Path.home() / ".sotong"
WIN = sys.platform == "win32"
sys.path[:0] = [str(ENGINE), str(ENGINE.parent)]   # python -I(Actions)는 스크립트 폴더도 넣지 않는다
import track_site  # noqa: E402  (engine/track_site.py — 문의 서버 등록, 자동차·법인 공용)
# 견본의 문구(소개·상황·FAQ·글)는 물려받고, 사람에 붙은 값은 비운다.
# 사진은 복사하지 않는다 — 앞 사람 얼굴이 따라오는 사고가 구조적으로 생길 수 없게(자동차 단지와 같은 규칙).
RESET = dict(years="", kakao_url="", channels=[], og_title="", og_description="", hero_caption="", hero_video="",
             badges=[], credentials_are_samples=False, naver_verification="", track_url="",
             google_verification="", bing_verification="", daum_verification="")   # 검색엔진 소유 확인값은 사이트마다 다르다(11/18)


def new_unit(name, given_path, domain=""):
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        sys.exit("세대 이름은 영문 소문자·숫자·하이픈만 됩니다(임시 주소 <이름>.pages.dev 가 됩니다). 예: corp-gwangju-munjin")
    u = UNITS / name
    if u.exists():
        sys.exit(f"이미 있는 세대입니다: units/{name}")
    sample = json.loads((SAMPLE / "config.json").read_text(encoding="utf-8"))
    given = json.loads(Path(given_path).read_text(encoding="utf-8"))
    need = [k for k in ("name", "phone", "region", "region_official") if not str(given.get(k, "")).strip()]
    if need:
        sys.exit(f"받은값에 빠진 것: {', '.join(need)} (견본 인물 값으로 채우지 않습니다)")
    cfg = {k: v for k, v in sample.items() if k not in ("hero_image", "hero_cutout")}
    cfg.update(RESET)
    cfg.update(given)
    cfg.update(pages_project=name, site_url=f"https://{domain.strip('/') if domain else name + '.pages.dev'}")
    shown = json.dumps({k: v for k, v in cfg.items() if not k.endswith("_note")}, ensure_ascii=False)
    left = [w for w in (sample["name"], "수도권") if w in shown]
    if left:
        sys.exit(f"견본 사람·지역 말이 남았습니다: {left} — 받은값에서 그 칸(career·faq 등)을 이 사람 것으로 덮어 주세요")
    (u / "assets").mkdir(parents=True)
    (u / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(SAMPLE / "content", u / "content")
    shutil.copy2(ENGINE / "unit_files" / "build.py", u / "build.py")
    print(f"입주 → units/{name}  ({cfg['site_url']})\n"
          f"다음: assets/ 에 본인 사진 → make_og_card.py → "
          f"npx wrangler pages project create {name} --production-branch=main --force (처음 한 번) → deploy.py {name}")


def corp_units(name):
    if (Path(name) / "config.json").exists() and not (UNITS / name).exists():   # Actions: deploy.py . (세대 저장소 안)
        return [Path(name).resolve()]
    us = [u for u in sorted(UNITS.iterdir()) if (u / "config.json").exists()
          and json.loads((u / "config.json").read_text(encoding="utf-8")).get("pages_project")]
    us = us if name == "all" else [u for u in us if u.name == name]
    return us or sys.exit(f"법인 단지 세대가 없습니다: {name}")


def ping_indexnow(u, site):
    """올린 뒤 sitemap 주소 전부를 IndexNow 로 한 번에 알린다(빙·네이버·얀덱스 등 참여 엔진이 서로 나눠 받음).
    임시 주소(noindex)는 색인 대상이 아니라 건너뛴다."""
    if "noindex" in (u / "dist" / "index.html").read_text(encoding="utf-8"):
        return "임시 주소(noindex)라 건너뜀"
    key = next((p.stem for p in u.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}", p.stem)), None)
    urls = re.findall(r"<loc>([^<]+)</loc>", (u / "dist" / "sitemap.xml").read_text(encoding="utf-8"))
    body = json.dumps({"host": urlparse(site).netloc, "key": key, "keyLocation": f"{site}/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        return f"{len(urls)}개 → {urllib.request.urlopen(req, timeout=15).status}"
    except urllib.error.HTTPError as e:
        return f"{len(urls)}개 → {e.code} (실패, 사이트는 올라감)"
    except Exception as e:
        return f"실패 {e} (사이트는 올라감)"


def run(cmd, cwd, inp=None, env=None):
    # shell 은 Windows 의 npx(.cmd)에만 — 리눅스(Actions)에서 목록을 shell 로 넘기면 첫 낱말만 돈다
    r = subprocess.run(cmd, cwd=cwd, input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=WIN and cmd[0] == "npx", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def build_cmd(u):
    # 세대 폴더의 build.py 가 아니라 엔진을 직접 부른다. 세대 저장소 파일은 고객 관리 화면·글해줌 앱이 쓸 수 있으므로
    # Actions 에서 비밀값 옆에 실행하면 열쇠를 빼 갈 수 있다(11/20 보안 검토). -I: 세대 폴더의 같은 이름 .py 가 끼어들지 못하게.
    return [sys.executable, "-I", "-X", "utf8", "-c",
            f"import sys; sys.path.insert(0, {str(ENGINE)!r}); import build; build.use_unit({str(u)!r}); build.main()"]


def check_unit(u):
    """올리기 전 세대 데이터 검사 — 세대 저장소는 고객 관리 화면 열쇠·글해줌 앱이 쓸 수 있다(11/20 보안 검토).
    엔진은 설정·글을 걸러내지 않고 화면에 찍고, 보안 머리글은 페이지 안 스크립트·on…= 지문을 허용하며, 사진·카드는 경로대로 복사한다.
    그래서 데이터 칸이 코드나 비밀 파일로 번지는 길을 여기서 막는다. 문제 목록을 돌려준다(비면 통과). 기존 세대 6곳은 전부 통과."""
    from publish import SAFE_HREF
    bad = [f"바로가기(심볼릭 링크) {p.relative_to(u)}" for p in u.rglob("*")
           if p.is_symlink() and p.relative_to(u).parts[0] not in ("_engine", "법인도구", ".git", "dist")]
    cfg = json.loads((u / "config.json").read_text(encoding="utf-8"))

    def walk(v, k):
        if isinstance(v, dict):
            [walk(x, kk) for kk, x in v.items()]
        elif isinstance(v, list):
            [walk(x, k) for x in v]
        elif isinstance(v, str) and not k.endswith("_note") and re.search(r"[\"<>]", v):
            bad.append(f"config {k}: 따옴표·꺾쇠")
        elif (isinstance(v, str) and v and k.endswith(("url", "_image", "_video", "_cutout"))
              and not (SAFE_HREF.fullmatch(v) or re.fullmatch(r"(tel|mailto):[\w@.+-]+", v))):
            bad.append(f"config {k}: 주소는 http(s)·상대 주소·tel·mailto 만")   # javascript: 등이 href·src 로 들어가지 않게
    walk(cfg, "")
    # 빌드 중 세대 폴더엔 비공개 도구 원본(법인도구/web)과 .git 도 있다 — 카톡 카드는 assets/ 안 사진 파일만
    og = (u / (cfg.get("og_image") or "assets/og-card.jpg")).resolve()
    if not og.is_relative_to((u / "assets").resolve()) or og.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        bad.append("config og_image 는 assets/ 안 사진(jpg·png·webp)만")
    for md in sorted((u / "content").glob("*.md")):
        t = md.read_text(encoding="utf-8")
        head = t.split("\n---", 1)[0] if t.startswith("---") else ""
        if "<" in t or '"' in head:
            bad.append(f"content/{md.name}: 태그(<) 또는 머리말 따옴표")
        bad += [f"content/{md.name}: 링크 {h[:40]}" for h in re.findall(r"\]\(([^)]*)\)", t) if not SAFE_HREF.fullmatch(h)]
    return bad


def sh(cmd, cwd, inp=None):
    code, out = run(cmd, cwd, inp)
    if code:
        sys.exit(f"실패: {' '.join(cmd[:5])}\n{out[-600:]}")
    return out


WORKFLOW = """# 이 세대 저장소엔 설정·사진·글만 있다. 지을 때 엔진(공개 sotong-apt)과 업무 도구(비공개 corp-tool 의 web 만)를 받아 와서 짓는다.
# 글해줌이 inbox/ 에 글을 넣거나, 관리 화면이 저장하거나, deploy.py all 이 부르면 돈다. 만든 곳: engine/corp/deploy.py open
name: build
on:
  push:
    branches: [main]
    paths-ignore: ["inbox/*.jpg", "inbox/*.jpeg", "inbox/*.png", "inbox/*.webp"]   # 글해줌은 사진을 먼저 한 장씩, json 을 마지막에 올린다 — json 커밋에서 한 번만 돈다
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: build
  cancel-in-progress: false   # 올리는 도중에 끊지 않는다. 줄 선 실행은 최신 하나만 남으니 연달아 온 글이 저절로 한 번에 묶인다
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: %(owner)s/sotong-apt
          path: _engine
          persist-credentials: false
      - uses: actions/checkout@v4
        with:
          repository: %(owner)s/corp-tool
          path: 법인도구
          ssh-key: ${{ secrets.CORP_TOOL_KEY }}
          persist-credentials: false   # 받자마자 열쇠를 지운다
          sparse-checkout: web
          filter: blob:none
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      # 여기부터 엔진 코드만 돈다 — 이 저장소의 build.py 등은 실행하지 않는다(고객·글해줌이 쓸 수 있는 파일이라)
      - id: inbox
        continue-on-error: true
        run: python -I -X utf8 _engine/engine/corp/publish.py --inbox --unit .
      - run: python -I -X utf8 _engine/engine/corp/deploy.py .
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      - if: steps.inbox.outcome == 'failure'
        run: echo "글해줌 글 중 심의 보류·거절이 있습니다 — 저장소 _보류/ 를 보세요" && exit 1
""" % {"owner": OWNER}
GITIGNORE = "dist/\n_engine/\n법인도구/\n__pycache__/\n.wrangler/\n_받은자료/\n도구_비밀번호.txt\n고객에게_보낼_안내.txt\n심의체크리스트.txt\n"


def need_keys():
    need = {"cloudflare_token.txt": "Cloudflare API 토큰 (Pages 편집)", "cloudflare_account.txt": "Cloudflare 계정 ID",
            "corp_tool_key": "corp-tool 읽기 전용 배포 열쇠"}
    miss = [f"{KEYS / k} — {v}" for k, v in need.items() if not (KEYS / k).exists()]
    if miss:
        sys.exit("처음 한 번 열쇠 준비가 필요합니다 → python -X utf8 deploy.py setup\n  " + "\n  ".join(miss))


def setup():
    """처음 한 번: corp-tool 읽기 전용 배포 열쇠를 만들어 걸고, Cloudflare 열쇠 자리를 알려 준다."""
    KEYS.mkdir(exist_ok=True)
    k = KEYS / "corp_tool_key"
    if not k.exists():
        sh(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "corp-units-build-read", "-f", str(k)], KEYS)
        sh(["gh", "repo", "deploy-key", "add", f"{k}.pub", "-R", f"{OWNER}/corp-tool", "--title", "corp units build (read only)"], KEYS)
        print(f"corp-tool 읽기 전용 배포 열쇠 → {k} (저장소엔 공개 열쇠만 걸림, 쓰기 불가)")
    for f, how in (("cloudflare_token.txt", "dash.cloudflare.com → 내 프로필 → API 토큰 → 토큰 만들기 → 사용자 지정: 계정 › Cloudflare Pages › 편집 → 만든 값을 이 파일에"),
                   ("cloudflare_account.txt", "dash.cloudflare.com 첫 화면 오른쪽 '계정 ID' 를 이 파일에 (npx wrangler whoami 에도 나옴)"),
                   ("tools_api_key.txt", "(login 때만) 글해줌 서버 .env 의 TOOLS_API_KEY 값을 이 파일에"),
                   ("github_app.json", "(글해줌 연결) python -X utf8 engine/github_app.py — 브라우저에서 [Create] 한 번")):
        print(f"{'있음' if (KEYS / f).exists() else '없음'}  {KEYS / f}" + ("" if (KEYS / f).exists() else f"\n      {how}"))


def tools_secret(project, cwd, name, value):
    sh(["npx", "--yes", "wrangler", "pages", "secret", "put", name, f"--project-name={project}"], cwd, inp=value)


def tools_api_key():
    # 글해줌 서버 .env 의 TOOLS_API_KEY 와 같은 값이어야 문이 열린다. 서버 주소는 공개 엔진에 적지 않는다(Cloudflare 뒤 원래 주소 숨김, 11/17).
    p = KEYS / "tools_api_key.txt"
    if not p.exists():
        sys.exit(f"{p} 가 없습니다 — 글해줌 서버 .env 의 TOOLS_API_KEY 값을 이 파일에 한 번 넣어 주세요")
    return p.read_text(encoding="utf-8").strip()


def login(name, email):
    """도구 문을 '이 고객의 글해줌 계정'으로 — 구독이 끊기면 하루 안에 문이 닫힌다(판매용). 비밀번호 문은 지운다."""
    u = UNITS / name
    project = json.loads((u / "config.json").read_text(encoding="utf-8"))["pages_project"]
    tools_secret(project, u, "TOOLS_API_KEY", tools_api_key())
    tools_secret(project, u, "TOOLS_OWNER_EMAIL", email.strip())
    run(["npx", "--yes", "wrangler", "pages", "secret", "delete", "TOOLS_PASSWORD", f"--project-name={project}"], u, inp="y\n")
    print(f"{name}: 도구 문 = 글해줌 로그인({email.strip()}) — 다음 배포부터 적용(deploy.py {name})")


def open_unit(name, given=None, domain=""):
    """새 고객 개통 한 번에. 끝난 단계는 건너뛰므로 중간에 멈추면 같은 명령을 다시 치면 이어서 간다.
    입주 → 연결 파일·자동 빌드 → 이 PC 시험 빌드 → 비공개 저장소 → 비밀값 → Cloudflare·도구 문 → 문의 서버 → 올리기(Actions 가 지음)."""
    need_keys()
    u = UNITS / name
    if not (u / "config.json").exists():
        if not given:
            sys.exit("처음 개통이면 받은값.json 이 필요합니다: deploy.py open <세대> 받은값.json [도메인]")
        new_unit(name, given, domain)
    repo = f"{OWNER}/{name}"
    cfg = json.loads((u / "config.json").read_text(encoding="utf-8"))
    cfg.update(admin_repo=repo, track_url=cfg.get("track_url") or TRACK_URL)
    (u / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("[1/7] 연결 파일·자동 빌드")
    shutil.copy2(ENGINE / "unit_files" / "build.py", u / "build.py")   # 이 PC에서 손으로 지을 때용(Actions 는 엔진을 직접 부름)
    (u / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (u / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (u / ".github" / "workflows" / "build.yml").write_text(WORKFLOW, encoding="utf-8")

    print("[2/7] 이 PC에서 지어 보기 (세대 데이터 검사·심의 자동점검·도구 문 검사)")
    if check_unit(u):
        sys.exit(f"{name}: 세대 데이터 검사에 걸림\n  " + "\n  ".join(check_unit(u)[:20]))
    code, out = run(build_cmd(u), u)
    if code or "위반 있음" in out:
        sys.exit(f"{name}: 빌드 실패 또는 심의 점검 위반 — 고치고 다시\n{out[-600:]}")
    sh(["node", str(ENGINE / "test_tools_gate.mjs")], u)

    print(f"[3/7] 비공개 저장소 {repo}")
    if not (u / ".git").exists():
        sh(["git", "init", "-b", "main"], u)
    if run(["gh", "repo", "view", repo], u)[0]:
        sh(["gh", "repo", "create", repo, "--private", "--description", f"{cfg['name']} 개인 홈페이지 (법인 단지 세대)"], u)

    print("[4/7] 자동 빌드 비밀값 (값은 화면에 안 나옴)")
    for secret, f in (("CLOUDFLARE_API_TOKEN", "cloudflare_token.txt"), ("CLOUDFLARE_ACCOUNT_ID", "cloudflare_account.txt"),
                      ("CORP_TOOL_KEY", "corp_tool_key")):
        sh(["gh", "secret", "set", secret, "-R", repo], u, inp=(KEYS / f).read_text(encoding="utf-8"))

    print(f"[5/7] Cloudflare Pages {cfg['pages_project']} · 도구 문")
    code, out = run(["npx", "--yes", "wrangler", "pages", "project", "create", cfg["pages_project"],
                     "--production-branch=main", "--force"], u)   # 4.158 부터 처음 만들 때 --force 필요
    if code and "already exists" not in out:
        sys.exit(f"Pages 프로젝트를 만들지 못했습니다\n{out[-600:]}")
    pw_file = u / "도구_비밀번호.txt"
    if not pw_file.exists():   # 첫날은 비밀번호 문. 고객 글해줌 계정이 생기면 deploy.py login 으로 바꾼다
        pw = next(p for p in iter(lambda: secrets.token_hex(9), None) if re.search(r"\d", p) and re.search(r"[a-f]", p))
        tools_secret(cfg["pages_project"], u, "TOOLS_PASSWORD", pw)
        pw_file.write_text(f"{cfg['site_url']}/tools/ — 비밀번호 {pw}\n(저장소에 안 올라감. 고객께는 카톡 1:1 로만. "
                           f"글해줌 계정이 생기면 deploy.py login {name} <메일>)\n", encoding="utf-8")

    print("[6/7] 문의 서버 등록")
    track_site.register(cfg["site_url"], {"repo": repo, "name": cfg["name"]})
    app_add(repo, u)

    print("[7/7] 올리기 — 저장소에 올리면 Actions 가 짓고 Cloudflare 로 (2~4분)")
    sh(["git", "add", "-A"], u)
    run(["git", "commit", "-m", f"{cfg['name']} 홈페이지 개통"], u)   # 다시 칠 때는 바뀐 게 없을 수 있다
    if run(["git", "remote", "get-url", "origin"], u)[0]:
        sh(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"], u)
    sh(["git", "push", "-u", "origin", "main"], u)
    print(f"""
개통 끝 — 2~4분 뒤 {cfg['site_url']}/   (진행: gh run watch -R {repo})
 · 도구 비밀번호: {pw_file.name} (카톡 1:1)
 · 본인 사진이 오면: assets/ 에 넣고 make_og_card.py {u} → 커밋·push (Actions 가 다시 지음)
 · 글해줌 매장 → 홈페이지 연결: 종류 '법인 단지' · 저장소 {repo} (글은 inbox/ 로)
 · 도메인이 오면: config 의 site_url 을 새 주소로 → 커밋·push → Pages 사용자 지정 도메인 연결 → 실주소 audit FAIL 0
 · 텔레그램 연결은 넘겨드리는 날 고객 폰으로 (tg_link.py)""")


def app_add(repo, cwd):
    """글해줌 GitHub 앱이 이 저장소에 글을 넣을 수 있게 설치 목록에 더한다(앱이 아직 없으면 건너뜀 — github_app.py)."""
    app = KEYS / "github_app.json"
    if not app.exists():
        print("  글해줌 GitHub 앱 없음 — 건너뜀 (만들기: python -X utf8 engine/github_app.py)")
        return
    slug = json.loads(app.read_text(encoding="utf-8"))["slug"]
    iid = sh(["gh", "api", "/user/installations", "--jq", f'.installations[] | select(.app_slug=="{slug}") | .id'], cwd).strip()
    rid = sh(["gh", "api", f"repos/{repo}", "--jq", ".id"], cwd).strip()
    if not iid:
        print(f"  앱 {slug} 이 아직 설치 안 됨 — https://github.com/apps/{slug}/installations/new 에서 '선택한 저장소'로 설치")
        return
    sh(["gh", "api", "-X", "PUT", f"/user/installations/{iid}/repositories/{rid}"], cwd)
    print(f"  글해줌 앱 {slug} 에 {repo} 추가")


if __name__ == "__main__":
    if len(sys.argv) < 2 or (sys.argv[1] == "new" and len(sys.argv) < 4):
        sys.exit(__doc__)
    if sys.argv[1] == "new":
        sys.exit(new_unit(*sys.argv[2:5]))
    if sys.argv[1] in ("open", "setup", "login"):
        if (sys.argv[1] == "open" and len(sys.argv) < 3) or (sys.argv[1] == "login" and len(sys.argv) < 4):
            sys.exit(__doc__)
        sys.exit({"open": open_unit, "setup": setup, "login": login}[sys.argv[1]](*sys.argv[2:5]))
    failed = []
    for u in corp_units(sys.argv[1]):
        cfg = json.loads((u / "config.json").read_text(encoding="utf-8"))
        project, site = cfg["pages_project"], cfg["site_url"].rstrip("/")
        print(f"[{u.name}] → {project}")
        if cfg.get("admin_repo") and not os.environ.get("GITHUB_ACTIONS"):
            # 실고객 세대의 원본은 저장소다. 이 PC 사본으로 올리면 글해줌이 넣은 새 글이 사라진다 → Actions 에 다시 짓기만 부탁
            code, out = run(["gh", "workflow", "run", "build", "-R", cfg["admin_repo"]], u)
            print("    저장소에 다시 짓기 요청:", "됨" if not code else out[-300:])
            continue
        if os.environ.get("GITHUB_ACTIONS"):
            # Cloudflare 열쇠는 계정 전체용이다(Pages 는 프로젝트 하나로 좁힌 열쇠가 없다). 올릴 곳은 고객이 못 바꾸는 저장소 이름으로 고정한다.
            pinned = os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1]
            if project != pinned:
                sys.exit(f"config 의 pages_project({project})가 저장소 이름({pinned})과 다릅니다 — 남의 사이트에 올리지 않습니다")
        bad = check_unit(u)
        if bad:
            sys.exit(f"{u.name}: 세대 데이터 검사에 걸려 올리지 않습니다\n  " + "\n  ".join(bad[:20]))
        no_keys = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDFLARE_")}   # 짓기·검사엔 열쇠를 안 준다 — wrangler 만
        code, out = run(build_cmd(u), u, env=no_keys)
        print("   ", " / ".join(l for l in out.splitlines() if l.startswith(("빌드 완료", "도구 코드"))) or out[-400:])
        if code or "위반 있음" in out:
            sys.exit(f"{u.name}: 빌드 실패 또는 심의 점검 위반 — 올리지 않습니다")
        code, out = run(["node", str(ENGINE / "test_tools_gate.mjs")], u, env=no_keys)
        if code:
            sys.exit(f"{u.name}: 도구 문 자체검사 실패 — 올리지 않습니다\n{out[-600:]}")
        # wrangler 는 세대 폴더 밖에서 — npx 는 위로 올라가며 node_modules 를 찾으므로 저장소에 심은 가짜 wrangler 가 돌 수 있다
        code, out = run(["npx", "--yes", "wrangler", "pages", "deploy", str(u / "dist"), f"--project-name={project}",
                         "--branch=main", "--commit-dirty=true"], os.environ.get("RUNNER_TEMP") or ENGINE)
        print("   ", (out.strip().splitlines() or ["(출력 없음)"])[-1])
        if code:
            sys.exit(f"{u.name}: 올리기 실패\n{out[-600:]}")
        print("    IndexNow:", ping_indexnow(u, site))
        # 올라간 실물을 AI 로봇처럼 들어가 본다 — 도메인 안내소를 Cloudflare 로 옮긴 날 'AI 로봇 막기'가 켜지는 사고를 여기서 잡는다.
        if AUDIT.exists():
            code, out = run([sys.executable, "-X", "utf8", str(AUDIT), "dist", site], u)
            print("    점검:", (out.strip().splitlines() or ["(출력 없음)"])[-1])
            if code:   # 이미 올라간 뒤라 다른 세대는 계속 올리고, 끝에 모아서 알린다
                failed.append(u.name)
                print("\n".join(l for l in out.splitlines() if "FAIL" in l))
    if failed:
        sys.exit(f"올라간 사이트 점검 FAIL 세대: {', '.join(failed)} — 고치고 다시 올리세요")
