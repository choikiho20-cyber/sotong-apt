# -*- coding: utf-8 -*-
"""글해줌이 넣어 둔 글(inbox/*.json)을 이 세대 홈페이지 글로 옮긴다 — 엔진의 publish.py 를 부르는 연결 파일.
GitHub Actions 가 지을 때마다 먼저 부른다(python publish.py --inbox). 손으로: python publish.py --json 글.json --no-deploy"""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ENGINE = next((p for p in (UNIT.parents[1] / "engine" / "corp", UNIT / "_engine" / "engine" / "corp")
               if (p / "publish.py").exists()), None)
if ENGINE is None:
    sys.exit("엔진(sotong-apt/engine/corp)을 찾지 못했습니다.")
sys.path.insert(0, str(ENGINE))
import publish  # noqa: E402  (엔진의 publish.py)

if __name__ == "__main__":
    publish.use_unit(UNIT)
    publish.main()
