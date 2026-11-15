# -*- coding: utf-8 -*-
"""이 세대(법인영업 설계사 한 명)의 홈페이지를 짓는다. 코드는 여기 없다 — 엔진(sotong-apt/engine/corp)을 부르는 연결 파일."""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ENGINE = UNIT.parents[1] / "engine" / "corp"
if not (ENGINE / "build.py").exists():
    sys.exit("엔진(sotong-apt/engine/corp)을 찾지 못했습니다.")
sys.path.insert(0, str(ENGINE))
import build  # noqa: E402  (엔진의 build.py)

if __name__ == "__main__":
    build.use_unit(UNIT)
    build.main()
