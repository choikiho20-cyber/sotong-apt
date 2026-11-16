# -*- coding: utf-8 -*-
"""법인 단지 짓고 올리기.  python -X utf8 deploy.py <세대|all>
새 세대 입주.            python -X utf8 deploy.py new <세대> 받은값.json [도메인]
세대 config.json 의 pages_project(Cloudflare Pages 이름)가 있는 세대가 법인 단지다. 자동차 단지는 cf_project·admin_repo(engine/car/apt.py).
업무 도구(법인도구/web)·엔진을 고쳤으면 all — 전 세대가 같은 도구로 다시 지어진다."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
UNITS = ENGINE.parents[1] / "units"
SAMPLE = UNITS / "demo-corp"
# 견본의 문구(소개·상황·FAQ·글)는 물려받고, 사람에 붙은 값은 비운다.
# 사진은 복사하지 않는다 — 앞 사람 얼굴이 따라오는 사고가 구조적으로 생길 수 없게(자동차 단지와 같은 규칙).
RESET = dict(years="", kakao_url="", channels=[], og_title="", og_description="", hero_caption="", hero_video="",
             badges=[], credentials_are_samples=False, naver_verification="", track_url="")


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
    us = [u for u in sorted(UNITS.iterdir()) if (u / "config.json").exists()
          and json.loads((u / "config.json").read_text(encoding="utf-8")).get("pages_project")]
    us = us if name == "all" else [u for u in us if u.name == name]
    return us or sys.exit(f"법인 단지 세대가 없습니다: {name}")


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=(cmd[0] == "npx"))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


if __name__ == "__main__":
    if len(sys.argv) < 2 or (sys.argv[1] == "new" and len(sys.argv) < 4):
        sys.exit(__doc__)
    if sys.argv[1] == "new":
        sys.exit(new_unit(*sys.argv[2:5]))
    for u in corp_units(sys.argv[1]):
        project = json.loads((u / "config.json").read_text(encoding="utf-8"))["pages_project"]
        print(f"[{u.name}] → {project}")
        code, out = run([sys.executable, "-X", "utf8", "build.py"], u)
        print("   ", " / ".join(l for l in out.splitlines() if l.startswith(("빌드 완료", "도구 코드"))) or out[-400:])
        if code or "위반 있음" in out:
            sys.exit(f"{u.name}: 빌드 실패 또는 심의 점검 위반 — 올리지 않습니다")
        code, out = run(["node", str(ENGINE / "test_tools_gate.mjs")], u)
        if code:
            sys.exit(f"{u.name}: 도구 문 자체검사 실패 — 올리지 않습니다\n{out[-600:]}")
        code, out = run(["npx", "--yes", "wrangler", "pages", "deploy", "dist", f"--project-name={project}", "--commit-dirty=true"], u)
        print("   ", (out.strip().splitlines() or ["(출력 없음)"])[-1])
        if code:
            sys.exit(f"{u.name}: 올리기 실패\n{out[-600:]}")
