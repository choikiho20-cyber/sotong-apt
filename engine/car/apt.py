# -*- coding: utf-8 -*-
"""자동차 영업사원 아파트 관리 — 대표님·Claude 가 쓰는 명령 하나.

  python -X utf8 apt.py list                      전체 명단 (메이커 → 지역 → 이름) + 명단.csv
  python -X utf8 apt.py build <세대|all>          짓기만
  python -X utf8 apt.py deploy <세대|all>         짓고 올리기 — 견본(cf_project)은 Cloudflare, 실고객은 GitHub 다시 짓기
  python -X utf8 apt.py new <세대이름> --config 받은값.json [--domain 도메인] [--local]
                                                  새 영업사원 입주 (GitHub 저장소 만들기는 대표님 터미널에서)

엔진(build·화면 틀·관리 화면)을 고친 뒤 'deploy all' 한 번이면 전 세대가 새 기준으로 다시 지어진다.
"""
import argparse
import csv
import json
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENGINE = Path(__file__).resolve().parent
APT = ENGINE.parents[1]
UNITS = APT / "units"
TRACK = APT.parent / "car-track"
OWNER = "choikiho20-cyber"
AUDIT = Path.home() / ".claude" / "skills" / "homepage-seo" / "audit.py"   # 홈페이지 검색 점검표(FAIL 0 이어야 납품)
ENGINE_REPO = f"{OWNER}/sotong-apt"
WIN = sys.platform == "win32"


def sh(cmd, cwd, check=True):
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=WIN and cmd[0] in ("npx", "gh"))
    if r.returncode and check:
        sys.exit(f"실패: {' '.join(cmd)}\n{(r.stdout + r.stderr)[-800:]}")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def cfg_of(unit):
    return json.loads((unit / "config.json").read_text(encoding="utf-8"))


def units(name):
    if name == "all":
        return sorted(p for p in UNITS.iterdir() if (p / "config.json").exists())
    u = UNITS / name
    if not (u / "config.json").exists():
        sys.exit(f"세대가 없습니다: units/{name}")
    return [u]


def cmd_list(_a):
    rows = []
    for u in units("all"):
        c = cfg_of(u)
        rows.append({"메이커": c.get("brand", ""), "지역": c.get("region", ""), "이름": c.get("name", ""),
                     "소속": c.get("dealership", ""), "주소": c.get("site_url", ""),
                     "구분": "견본" if c.get("cf_project") else ("실고객" if c.get("admin_repo") else "준비 중"),
                     "저장소": c.get("admin_repo", ""), "세대": u.name})
    rows.sort(key=lambda r: (r["메이커"], r["지역"], r["이름"]))
    with open(APT / "명단.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]) if rows else ["세대"])
        w.writeheader(); w.writerows(rows)
    for r in rows:
        print(f"{r['메이커']:<6} {r['지역']:<6} {r['이름']:<6} {r['구분']:<4} {r['주소']}")
    print(f"\n총 {len(rows)}세대 → 명단.csv")


def build_unit(u):
    ok, out = sh([sys.executable, "-X", "utf8", "build.py"], u, check=False)
    last = [l for l in out.splitlines() if l.startswith(("빌드 완료", "[X]"))]
    print("   ", " / ".join(last) or out[-300:])
    if not ok or "위반 있음" in out:
        sys.exit(f"{u.name}: 빌드 실패 또는 광고 점검 위반 — 올리지 않습니다")


def cmd_build(a):
    for u in units(a.unit):
        print(f"[{u.name}]")
        build_unit(u)


def cmd_deploy(a):
    failed = []
    for u in units(a.unit):
        c = cfg_of(u)
        print(f"[{u.name}]")
        if c.get("cf_project"):            # 판매 전 견본: 이 PC에서 짓고 Cloudflare 로
            build_unit(u)
            sh(["npx", "--yes", "wrangler", "pages", "deploy", "dist", f"--project-name={c['cf_project']}",
                "--commit-dirty=true"], u)
        elif c.get("admin_repo"):          # 실고객: 저장소의 Actions 가 최신 엔진을 받아 다시 짓는다
            sh(["gh", "workflow", "run", "build", "-R", c["admin_repo"]], u)
        else:
            print("    배포 대상 아님(cf_project·admin_repo 둘 다 없음)")
            continue
        # 올라간 실주소를 AI 로봇처럼 들어가 본다 — 도메인 안내소를 Cloudflare 로 옮긴 날 'AI 로봇 막기'가 켜지는 사고를 잡는다.
        if AUDIT.exists() and (u / "dist").exists() and c.get("site_url"):
            ok, out = sh([sys.executable, "-X", "utf8", str(AUDIT), "dist", c["site_url"].rstrip("/")], u, check=False)
            print("    점검:", out.splitlines()[-1] if out else "")
            if not ok:
                failed.append(u.name)
                print("\n".join(l for l in out.splitlines() if "FAIL" in l))
    if failed:
        sys.exit(f"점검 FAIL 세대: {', '.join(failed)} — 고치고 다시 올리세요")


WORKFLOW = """# 이 세대 저장소엔 설정·사진·글만 있다. 지을 때 엔진(sotong-apt)을 받아 와서 짓는다.
# 엔진이 바뀌면 apt.py deploy all 이 이 워크플로를 다시 돌려 새 기준으로 다시 짓는다.
name: build
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: %s
          path: _engine
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pillow segno
      - run: python -X utf8 build.py
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.d.outputs.page_url }}
    steps:
      - id: d
        uses: actions/deploy-pages@v4
""" % ENGINE_REPO
GITIGNORE = "dist/\n_engine/\n__pycache__/\n_보류/\n고객에게_보낼_안내.txt\n"


def cmd_new(a):
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.unit):
        sys.exit("세대 이름은 영문 소문자·숫자·하이픈만 됩니다 (주소에 그대로 쓰입니다). 예: car-ulsan-hyundai-kimcheolsu")
    u = UNITS / a.unit
    if u.exists():
        sys.exit(f"이미 있는 세대입니다: units/{a.unit}")

    print(f"[1/5] 세대 만들기 → units/{a.unit}")
    cfg = json.loads((ENGINE / "config_template.json").read_text(encoding="utf-8"))
    if a.config:
        cfg.update(json.loads(Path(a.config).read_text(encoding="utf-8")))
    need = [k for k in ("name", "phone", "region", "brand", "lineup", "tagline", "intro", "years") if not str(cfg.get(k, "")).strip()]
    if need:
        sys.exit(f"--config 에 영업사원 값이 빠졌습니다: {', '.join(need)} (견본 인물 값으로 채우지 않습니다)")
    if not (ENGINE / "makers" / cfg.get("lineup", "") / "lineup.json").exists():
        have = sorted(p.name for p in (ENGINE / "makers").iterdir())
        sys.exit(f"config 의 lineup 이 메이커 목록에 없습니다: {cfg.get('lineup')} (있는 것: {', '.join(have)})")
    repo = f"{OWNER}/{a.unit}"
    site = f"https://{a.domain.strip('/')}" if a.domain else f"https://{OWNER}.github.io/{a.unit}"
    cfg.update(site_url=site, admin_repo=repo, admin_branch="main")
    cfg.pop("cf_project", None)
    cfg["offers"] = [o for o in cfg.get("offers", []) if not o.get("example")]
    (u / "assets").mkdir(parents=True)
    (u / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(ENGINE / "content_starter", u / "content")
    for f in ("build.py", "publish.py"):
        shutil.copy2(ENGINE / "unit_files" / f, u / f)
    (u / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (u / ".github" / "workflows").mkdir(parents=True)
    (u / ".github" / "workflows" / "build.yml").write_text(WORKFLOW, encoding="utf-8")
    key = secrets.token_hex(16)   # IndexNow 키는 세대마다. 커밋해 두지 않으면 Actions 가 빌드마다 새로 만든다
    (u / f"{key}.txt").write_text(key, encoding="utf-8")
    # 사진은 복사하지 않는다 — 앞 사람 사진이 따라오는 사고가 구조적으로 생길 수 없게.
    # 본인 사진이 오기 전엔 메이커 그림이 첫 화면을 채우고, 카톡 카드는 make_art 뒤에 나온다.

    print("[2/5] 빌드 시험")
    build_unit(u)
    sh(["git", "init", "-b", "main"], u)
    sh(["git", "add", "-A"], u)
    sh(["git", "commit", "-m", f"{cfg.get('name', a.unit)} 홈페이지 입주"], u)
    if a.local:
        print(f"\n--local: GitHub·서버 등록은 건너뜀 → units/{a.unit}")
        return

    print(f"[3/5] GitHub 공개 저장소 {repo}")
    sh(["gh", "repo", "create", repo, "--public", "--source", ".", "--push",
        "--description", f"{cfg.get('name', '')} {cfg.get('brand', '')} 영업사원 홈페이지"], u)
    ok, _ = sh(["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "build_type=workflow"], u, check=False)
    if not ok:
        print("  ! Pages 자동 전환 실패 — 저장소 Settings › Pages › Source 를 'GitHub Actions' 로")
    sh(["gh", "workflow", "run", "build", "-R", repo], u, check=False)

    print("[4/5] 문의·열람 서버 등록")
    toml = (TRACK / "wrangler.toml").read_text(encoding="utf-8")
    m = re.search(r"^SITES = '(.*)'$", toml, re.M)
    sites = json.loads(m.group(1))
    sites[re.sub(r"^https?://", "", site)] = {"repo": repo, "name": cfg.get("name", a.unit)}
    toml = toml[:m.start(1)] + json.dumps(sites, ensure_ascii=False, separators=(",", ":")) + toml[m.end(1):]
    (TRACK / "wrangler.toml").write_text(toml, encoding="utf-8")
    sh(["npx", "--yes", "wrangler", "deploy"], TRACK)

    print(f"""[5/5] 완료 — 1~2분 뒤 {site}/

남은 손작업
 1. 관리 화면 토큰: https://github.com/settings/personal-access-tokens/new
    저장소 {repo} 하나만 · Contents 읽기/쓰기 · 1년
 2. {site}/admin.html → 「관리자용」 토큰 → [이 기기 연결] → [비밀번호 정하기]
 3. 글해줌 매장 → 홈페이지 연결: 종류 static · 사이트 폴더 {u}
 4. 본인 사진·실적이 오면 assets/hero.jpg 넣고 카톡 카드(og-card.jpg) 만들기 → 커밋·push
 5. 넘겨드리는 날: 영업사원 폰으로 텔레그램 연결 2분 (홈페이지_안내서 5쪽)
""")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for c in ("build", "deploy"):
        sub.add_parser(c).add_argument("unit")
    n = sub.add_parser("new")
    n.add_argument("unit")
    n.add_argument("--config")
    n.add_argument("--domain")
    n.add_argument("--local", action="store_true")
    a = ap.parse_args()
    {"list": cmd_list, "build": cmd_build, "deploy": cmd_deploy, "new": cmd_new}[a.cmd](a)


if __name__ == "__main__":
    main()
