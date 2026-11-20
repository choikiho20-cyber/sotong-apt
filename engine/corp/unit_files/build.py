# -*- coding: utf-8 -*-
"""이 세대(법인 경영 컨설턴트 한 명)의 홈페이지를 짓는다. 코드는 여기 없다 — 엔진(sotong-apt/engine/corp)을 부르는 연결 파일.
엔진 위치: 대행 PC에선 ../../engine/corp, GitHub Actions에선 _engine/engine/corp (워크플로가 받아 둔다)."""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ENGINE = next((p for p in (UNIT.parents[1] / "engine" / "corp", UNIT / "_engine" / "engine" / "corp")
               if (p / "build.py").exists()), None)
if ENGINE is None:
    sys.exit("엔진(sotong-apt/engine/corp)을 찾지 못했습니다.")
sys.path.insert(0, str(ENGINE))
import build  # noqa: E402  (엔진의 build.py)

if __name__ == "__main__":
    build.use_unit(UNIT)
    build.main()
