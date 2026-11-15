# -*- coding: utf-8 -*-
"""법인 단지 짓고 올리기.  python -X utf8 deploy.py <세대|all>
세대 config.json 의 pages_project(Cloudflare Pages 이름)가 있는 세대가 법인 단지다. 자동차 단지는 cf_project·admin_repo(engine/car/apt.py).
업무 도구(법인도구/web)·엔진을 고쳤으면 all — 전 세대가 같은 도구로 다시 지어진다."""
import json
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
UNITS = ENGINE.parents[1] / "units"


def corp_units(name):
    us = [u for u in sorted(UNITS.iterdir()) if (u / "config.json").exists()
          and json.loads((u / "config.json").read_text(encoding="utf-8")).get("pages_project")]
    us = us if name == "all" else [u for u in us if u.name == name]
    return us or sys.exit(f"법인 단지 세대가 없습니다: {name}")


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=(cmd[0] == "npx"))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
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
