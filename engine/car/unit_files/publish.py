# -*- coding: utf-8 -*-
"""글해줌이 보낸 글 한 편을 이 세대 홈페이지에 올린다 — 엔진의 publish.py 를 부르는 연결 파일.
사용법은 엔진과 같다: python publish.py --json 글.json  /  --demo  /  --no-deploy"""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ENGINE = next((p for p in (UNIT.parents[1] / "engine" / "car", UNIT / "_engine" / "engine" / "car")
               if (p / "publish.py").exists()), None)
if ENGINE is None:
    sys.exit("엔진(sotong-apt/engine/car)을 찾지 못했습니다.")
sys.path.insert(0, str(ENGINE))
import publish  # noqa: E402  (엔진의 publish.py)

if __name__ == "__main__":
    publish.use_unit(UNIT)
    publish.main()
