# -*- coding: utf-8 -*-
"""문의·열람 서버(sotong-sites/car-track)에 세대를 등록한다 — 저장소(KV) 열쇠 site:<호스트>.
변수 SITES 는 5KB 한 칸이라 약 77곳에서 꽉 찬다. KV 는 곳당 열쇠 하나라 수천 곳도 그대로이고,
등록할 때 일꾼(car-track)을 다시 올리지 않는다(11/20). 자동차 apt.py · 법인 corp.py 가 같이 쓴다."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TRACK = Path(__file__).resolve().parents[2] / "car-track"


def register(site_url, info):
    host = re.sub(r"^https?://", "", site_url).rstrip("/")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)   # 값은 파일로 — 따옴표가 셸을 거치며 깨지지 않게
    r = subprocess.run(["npx", "--yes", "wrangler", "kv", "key", "put", f"site:{host}", "--binding=DB", "--remote", f"--path={f.name}"],
                       cwd=TRACK, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=sys.platform == "win32")
    Path(f.name).unlink(missing_ok=True)
    if r.returncode:
        sys.exit(f"문의 서버 등록 실패({host}): {(r.stdout + r.stderr)[-500:]}")
    print(f"  문의 서버 등록: site:{host}")
    return host
