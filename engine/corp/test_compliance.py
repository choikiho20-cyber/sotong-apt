# -*- coding: utf-8 -*-
"""심의 검사기 자기점검. 규칙을 손볼 때마다 `python test_compliance.py` 한 번.

규칙이 느슨해지면(놓침) 위반 문구가 그대로 배포되고,
빡빡해지면(오탐) 멀쩡한 문구까지 막혀 도구를 못 쓰게 된다. 양쪽 다 본다.
"""
import sys, importlib.util

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location("b", "build.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

check = lambda s: b.compliance_check(
    [{"slug": "t", "label": "test", "text": s}], {"life": [], "general": []})[1]

BAD = [  # 반드시 걸려야 하는 문구
    "무료 세무 진단 해 드립니다", "정관 점검 무료", "가지급금 진단 서비스",
    "세무 상담을 해 드립니다", "세무상담 해드립니다", "절세 컨설팅",
    "절세가 됩니다", "세금 없이 정리", "법인 등기를 대신 해 드립니다",
    "정관 변경을 처리해 드립니다", "세무 처리를 대행합니다",
    "환급률 120%", "업계 최고", "타사보다 유리", "무조건 받으실 수 있습니다",
    "리스크 방어 성공률 99.8%", "고객 만족도 98%", "상위 1% 설계사", "보험 리모델링 상담",
    "법인 명의로 낸 보험료의 처리", "보험설계사가 안내해 드립니다", "경영인정기보험 활용",
    "이익잉여금 절세 전문가", "법인 세무 전문가", "세금 컨설턴트",
    "미처분이익잉여금 세금없이 처리하는 전문가",   # 11/16 실제 요청 문구
]
GOOD = [  # 걸리면 안 되는 문구 (사이트 본문에 실제로 쓰는 표현)
    "관련 조문을 정리해 드립니다", "세무 상담을 해주시는 건가요?",
    "담당 세무사와 상의하십시오", "정관 점검이 아니라 조문 안내입니다",
    "가지급금이 남아 있는 법인", "증여세가 발생할 수 있습니다",
    "확인하실 항목을 목록으로 만들어 드립니다",
    "4대보험 가입 의무와 건강보험료 정산", "산업재해보상보험법상 보상", "국민건강보험공단 자료", "4대 보험 신고",
    "미처분이익잉여금 정리 설계 · 법인 경영 컨설턴트", "세무·법률 판단은 담당 전문가와 함께 하십시오",
    "쌓인 이익잉여금, 정리 방법을 숫자로 비교해 드립니다",
]

miss = [s for s in BAD if check(s)]
fp = [s for s in GOOD if not check(s)]
for s in miss: print("[놓침]", s)
for s in fp:   print("[오탐]", s)
assert not miss and not fp, "규칙 수정 필요"
print(f"통과 — 금지 {len(BAD)}건 전부 차단, 정상 {len(GOOD)}건 전부 통과")

# 푸터 분기: 보험 이야기가 있는 페이지만 의무 표시(풀 푸터)·'보험설계사' 호칭 (2026-10-31)
cfg = {"name": "홍길동"}
full, light = b._identity(cfg, True, ""), b._identity(cfg, False, "")
assert full["identity"] == "보험설계사 홍길동" and "확인필" in full["disclosure"]
assert light["identity"] == "홍길동" and "보험" not in light["disclosure"] and "privacy.html" in light["disclosure"]
assert b.mentions_insurance("법인 보험료 세무 처리") and not b.mentions_insurance("가지급금 인정이자 계산")
assert not b.mentions_insurance("4대보험 가입 의무와 고용보험료 · 건강보험료 정산"), "사회보험은 보험 이야기가 아니다"
print("통과 — 푸터 분기(보험 있음/없음, 사회보험 제외)")
