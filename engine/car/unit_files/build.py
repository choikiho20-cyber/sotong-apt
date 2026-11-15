# -*- coding: utf-8 -*-
"""이 세대(영업사원 한 명)의 홈페이지를 짓는다. 코드는 여기 없다 — 엔진(sotong-apt/engine/car)을 부르는 연결 파일.
엔진 위치: 대행 PC에선 ../../engine/car, GitHub Actions에선 _engine/engine/car (워크플로가 받아 둔다).
글해줌 발행기가 이 폴더에 build.py·publish.py·config.json 이 있는지 보고 발행하므로 지우지 말 것."""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ENGINE = next((p for p in (UNIT.parents[1] / "engine" / "car", UNIT / "_engine" / "engine" / "car")
               if (p / "build.py").exists()), None)
if ENGINE is None:
    sys.exit("엔진(sotong-apt/engine/car)을 찾지 못했습니다.")
sys.path.insert(0, str(ENGINE))
import build  # noqa: E402  (엔진의 build.py)

if __name__ == "__main__":
    build.use_unit(UNIT)
    build.main()
