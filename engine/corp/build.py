# -*- coding: utf-8 -*-
"""법인영업 설계사 개인 홈페이지 빌드. (10/29 개인판 build.py에서 옮겨 와 법인 규칙만 다시 얹음)

config.json + content/*.md + templates/ -> dist/
부수 산출물: sitemap.xml, robots.txt, 심의체크리스트.txt
사용법: 세대 폴더에서 python -X utf8 build.py (연결 파일이 이 엔진을 부른다)
      짓고 올리기까지: python -X utf8 sotong-apt/engine/corp/deploy.py <세대|all>
엔진(여기)=화면 틀·공용 그림·심의 규칙·도구 문, 세대(units/<세대>)=config.json·content/·assets/(본인 사진)
"""
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import sys
from datetime import date
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
# 업무 도구 원본. 공개 엔진 저장소에는 넣지 않고, 지을 때만 비공개 폴더에서 가져온다(코드 보호).
TOOLS = ENGINE.parents[2] / "법인도구" / "web"
ROOT = None      # 지금 짓는 세대 폴더 (use_unit 이 정한다)
DIST = None


def use_unit(path):
    global ROOT, DIST
    ROOT = Path(path).resolve()
    DIST = ROOT / "dist"

# 한글 Windows 콘솔(cp949)에서 체크리스트 출력이 깨지거나 죽지 않도록
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------- 미니 마크다운 변환 (의존성 없음) ----------
def inline(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return text


def md_to_html(md):
    html, para, ul, quote, table = [], [], [], [], []

    def flush():
        # 법인판 글은 조문 대조표가 많다. 표를 문단으로 흘리면 '| 내용 | 근거 |'가 그대로 찍힌다.
        if table:
            rows = [[c.strip() for c in r.strip("|").split("|")]
                    for r in table if not re.fullmatch(r"[\s|:-]+", r)]
            head, body = rows[0], rows[1:]
            html.append(
                '<div class="table-wrap"><table><thead><tr>'
                + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                + "</tbody></table></div>")
            table.clear()
        if para:
            html.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()
        if ul:
            html.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in ul) + "</ul>")
            ul.clear()
        if quote:
            html.append("<blockquote><p>" + inline(" ".join(quote)) + "</p></blockquote>")
            quote.clear()

    for line in md.splitlines():
        s = line.strip()
        if table and not s.startswith("|"):
            flush()
        if not s:
            flush()
        elif s.startswith("|"):
            if para or ul or quote:
                flush()
            table.append(s)
        elif s.startswith("### "):
            flush(); html.append(f"<h3>{inline(s[4:])}</h3>")
        elif s.startswith("## "):
            flush(); html.append(f"<h2>{inline(s[3:])}</h2>")
        elif s == "---":
            flush(); html.append("<hr>")
        elif s.startswith("> ") or s == ">":   # '>' 한 줄 = 인용 안 줄바꿈. 문단으로 흘리면 '>'가 그대로 찍힌다
            if para or ul:
                flush()
            quote.append(s[2:])
        elif s.startswith("- "):
            if para or quote:
                flush()
            ul.append(s[2:])
        else:
            if ul or quote:
                flush()
            para.append(s)
    flush()
    return "\n".join(html)


def parse_post(path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    meta = {}
    body = raw
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        body = m.group(2)
    meta["slug"] = path.stem
    meta["label"] = path.name
    meta["html"] = md_to_html(body)
    meta["text"] = body
    return meta


# 보험 이야기인지 가르는 기준. 법인영업판은 보험·설계사라는 말을 쓰지 않는다 — 클로징은 세무사와 현장에서 한다(10/31 대표님).
# 4대보험·고용보험·산재보험·건강보험·장기요양보험은 노무 글의 사회보험이라 제외한다(바로 앞 두 글자로 가른다).
INSURANCE = re.compile(r"(?<!4대)(?<!4대 )(?<!사회|고용|산재|건강|요양|실업|보상)보험|설계사")


def mentions_insurance(text):
    return bool(INSURANCE.search(text))


# ---------- 심의 체크리스트 (지시서 8-3) ----------
def compliance_check(posts, insurers, affiliation="", full_pages=None):
    # 법인영업판: 보험 금지어 + 세무/법률 자문으로 오인될 표현을 함께 검사한다.
    # 세무사법 제20조 제3항(2025.12.23 개정)은 무자격자가 "세무대리 업무를 취급하는 것으로
    # 오인될 우려가 있는 표시·광고"를 금지한다. 문구 하나가 위반이 될 수 있어 별도 규칙으로 둔다.
    # (법인판 insurers.json은 보험사가 아니라 공공 사이트 목록이라 '보험사명 미포함' 규칙은 두지 않는다)
    rules = [
        # 법인영업판의 첫 규칙. 보험 단어 하나가 '제도를 아는 사람'을 '보험 파는 사람'으로 바꾼다.
        ("보험 이야기 없음 (법인영업판은 보험을 말하지 않는다 — 클로징은 세무사와 현장에서)", INSURANCE.pattern),
        ("수익률·환급률 표현 없음", r"수익률|환급률"),
        ("보장 결과 단정 표현 없음", r"받으실 수 있습니다|보장해 드립|보장됩니다|확실히 받|무조건 받"),
        ("타사 비교 표현 없음", r"타사|다른 보험사보다"),
        ("최상급 표현 없음", r"1위|최고|최상급|유일한|업계 최|상위 ?\d+ ?%"),
        # 금감원이 '보험 리모델링' 광고를 부당 승환계약 유도로 지목해 왔다.
        ("승환 유도 표현 없음", r"리모델링|갈아타"),
        # 만족도·성공률 같은 비율은 실제 고객이어도 근거 자료 없이는 심의에서 반려된다.
        ("근거 없는 만족도·비율 표현 없음", r"만족도|성공률|승인률|지급률"),
        # 단어를 금지하는 게 아니라 "내가 해준다"는 형태만 잡는다.
        # (FAQ의 "세무 상담을 해주시는 건가요? → 아닙니다" 같은 부인 문장까지 잡으면 도구를 못 쓴다)
        ("세무대리 오인 표현 없음 (세무사법 제20조③)",
         r"세무\s?진단|절세\s?컨설팅|세무\s?컨설팅|무료\s?세무|"
         # 세금을 앞세운 직함 = 세무사와 비슷한 명칭·세무 자문 취급으로 오인(제20조②③). '세무·법률 판단은 담당 전문가'처럼 떨어진 말은 안 잡는다.
         r"(절세|세무|세금|조세)\s?(전문가|전문\s?컨설턴트|컨설턴트|상담사|플래너)|"
         r"정관\s?점검(?!이 아니)|가지급금\s?진단|"
         r"세무\s?(상담|점검)[을를]?\s*(해\s?드[리립]|진행해\s?드[리립]|도와\s?드[리립]|제공)"),
        ("절세 결과 단정 표현 없음",
         r"절세(가|를)?\s?(됩니다|가능합니다|보장)|세금\s?(없이|0원|안\s?냅)|"
         r"무조건\s?인정|한\s?번에\s?해결"),
        # "조문을 정리해 드립니다"는 정보 제공이라 걸면 안 되고,
        # "신고를/등기를 대신 해 드립니다"만 자격 침해가 된다.
        ("대행 표현 없음 (변호사법·세무사법)",
         r"(신고|신청|등기|정관\s?변경|세무\s?처리|절세)[를을]?\s*"
         r"(대신\s?)?(해\s?드[리립]|처리해\s?드[리립]|대행)"),
    ]
    manual = [
        "상품명 미포함",
        "인용 조문의 현행 여부 확인",
        "개정안과 현행법 구분 표기",
        "글 말미 자격 업무 안내 문구(자문 아님·신고·등기는 전문가) 포함",
        "제도 설명 글에 상품 결론을 붙이지 않음",
        "실제 고객 사례 미사용",
        "홈페이지에 보험·소속 표기가 없다는 것을 소속사 준법감시 담당에게 알림 (1회)",
    ]

    lines = [f"심의 제출용 자동 점검 결과  ({date.today().isoformat()} 빌드)", "=" * 40, ""]
    ok = True
    for label, pattern in rules:
        hits = []
        for p in posts:
            for i, line in enumerate(p["text"].splitlines(), 1):
                if re.search(pattern, line):
                    hits.append(f"    {p['label']} {i}행: {line.strip()[:60]}")
            head = " ".join(p.get(k, "") for k in ("title", "description"))   # 제목·요약은 첫 화면 목록에도 찍힌다
            if head and re.search(pattern, head):
                hits.append(f"    {p['label']} 제목/요약: {head[:60]}")
        if hits:
            ok = False
            lines.append(f"[X] {label} — 위반 {len(hits)}건")
            lines.extend(hits)
        else:
            lines.append(f"[O] {label}")
    if affiliation:
        lines.append("")
        lines.append(f"[!] 소속사명 표기 (의도적) — {affiliation}")
        lines.append("    노출 위치: 히어로 상단 뱃지, '이 사람은 누구인가' 소속란")
        lines.append("    소속 표기 자체는 금지 사항이 아닙니다. 오히려 금소법은 '소비자가 광고에서")
        lines.append("    보험회사를 올바르게 인지하는 것을 방해하는 행위'를 금지행위로 두고 있습니다.")
        lines.append("    다만 이 페이지는 업무광고이므로 소속사 준법감시인 확인(심의필)을 받아")
        lines.append("    번호를 config.json의 review_no에 기재하십시오. 회사 내부 브랜드 사용 규정은 별도 확인.")
        lines.append("    (회사가 표기 불가로 회신하면 affiliation을 비우고 재빌드 — 뱃지·소속란에서 함께 사라집니다)")

    if full_pages:
        lines.append("")
        lines.append(f"[!] 보험 이야기가 들어간 페이지 {len(full_pages)}개에 모집종사자 의무 표시(풀 푸터)와 '보험설계사' 호칭이 자동으로 붙었습니다")
        lines.extend(f"    {p}" for p in full_pages)
        lines.append("    원칙은 보험 이야기를 빼는 것입니다. 못 빼면 이 표시를 두고 소속사 준법감시 심의를 받아야 합니다.")
    lines.append("")
    lines.append("-- 자동 판정 불가, 발행 전 직접 확인 --")
    for label in manual:
        lines.append(f"[ ] {label}")
    lines.append("")
    lines.append("※ 본 점검은 심의 통과를 보장하지 않으며, 심의에 걸리기 쉬운 표현을 걸러주는 보조 도구입니다.")
    return "\n".join(lines), ok


# ---------- 고객에게 요청할 준비물 (대표가 대신 못 하는 것만) ----------
def client_todo(cfg, root, insured_pages=0):
    """설계사 본인만 줄 수 있는 항목을 추려 카톡에 붙여넣을 안내문을 만든다.

    한 번에 다 물어봐야 왕복이 한 번으로 끝난다. 지시서 4-1 '1건당 30분'은
    작업 시간이 아니라 대기 시간 때문에 깨진다.
    """
    hero = any((root / "assets" / f"hero{e}").exists() for e in (".webp", ".jpg", ".jpeg", ".png"))
    need = []
    if "xxxxxx" in cfg.get("kakao_url", ""):
        need.append((
            "카카오톡 오픈채팅 링크",
            "카톡 > 채팅 탭 > 오른쪽 위 [+] > 오픈채팅 > '1:1 채팅방' 선택\n"
            "     > 이름은 '법인 상담 문의' 정도로 > 완료 > 만들어진 방에서 링크 복사\n"
            "     ※ 본인 프로필 사진과 친구목록은 상대에게 보이지 않습니다\n"
            "     ※ 평소 쓰시는 카톡에서 그대로 알림 받고 답장하시면 됩니다",
        ))
    if not str(cfg.get("years", "")).strip():
        need.append(("이 일을 시작하신 연도", f"예) 2011년 — 홈페이지에 '{cfg['region']}에서 O년'으로 들어갑니다"))
    if "(" in cfg.get("registration_no", ""):
        need.append((
            "설계사 등록번호",
            "보험증권이나 상품설명서의 '설계사 정보'란에 적혀 있습니다\n"
            "     ※ 홈페이지 맨 아래 신분 표시 한 줄에 들어갑니다",
        ))
    if not hero:
        need.append(("사진 1장", "세로로 찍은 상반신 사진. 밝은 곳에서 찍은 것이면 좋습니다"))
    if cfg.get("credentials_are_samples") and (cfg.get("badges") or cfg.get("stats")):
        need.append((
            "자격·숫자 (있는 것만)",
            "MDRT·우수인증설계사 등 보유한 자격, 누적 상담 건수·청구 도와드린 건수 같은 숫자\n"
            "     ※ 근거를 댈 수 있는 것만 올라갑니다. 없으면 빼고 만듭니다\n"
            "     ※ 지금은 예시 숫자가 들어가 있고 화면에 '예시' 표시가 붙어 있습니다",
        ))
    if insured_pages and ("(" in cfg.get("agency_name", "(") or "(" in cfg.get("agency_reg_no", "(")):
        need.append((
            "소속 대리점 이름과 대리점 등록번호",
            "위촉계약서나 회사 전산의 '소속 정보'에 있습니다\n"
            f"     ※ 보험을 언급하는 페이지({insured_pages}개) 맨 아래 의무 표시란에 들어갑니다. 회사 준법감시 표준 문구가 있으면 같이 주세요",
        ))
    if insured_pages and ("(" in cfg.get("review_no", "") or not cfg.get("review_no")):
        need.append((
            "준법감시 확인필 번호와 유효기간",
            f"보험을 언급하는 페이지({insured_pages}개)를 회사 준법감시에 심의 요청하면 받는 번호입니다\n"
            "     ※ 심의 제출용 점검표는 저희가 만들어 드립니다",
        ))
    if cfg.get("cases_are_samples"):
        need.append((
            "청구 도와주신 사례 2~3건",
            "어떤 상황이었고 어떻게 처리하셨는지만 편하게 말씀해 주시면 정리해서 씁니다\n     ※ 고객 이름·병원명·날짜는 빼고, 게시해도 되는지 그분 동의만 받아 주세요\n     ※ 지금은 예시 3건이 올라가 있고 화면에 '예시' 표시가 붙어 있습니다",
        ))

    name = cfg.get("name", "고객")
    lines = [f"[{name} 님께 보낼 안내 — 카톡에 그대로 붙여넣으세요]", ""]
    lines += [f"{name} 님, 홈페이지는 이미 만들어 두었습니다.",
              "보시고 아래 것만 채우면 바로 공개됩니다.", ""]

    if need:
        lines += [f"■ {name} 님이 직접 해주셔야 하는 것 ({len(need)}가지)",
                  "   — 저희가 대신 할 수 없는 것들입니다", ""]
        for i, (title, how) in enumerate(need, 1):
            lines += [f"{i}. {title}", f"     {how}", ""]
    else:
        lines += ["■ 직접 해주실 것: 없습니다. 모두 받았습니다.", ""]

    lines += [
        "■ 권한만 주시면 저희가 해드리는 것",
        "   · 카카오톡 채널 개설·운영 → 채널 관리자로 초대만 해주시면 됩니다",
        "   · 구글 검색 등록 → 사용자 추가만 해주시면 됩니다",
        "   · 도메인 구입·연결·보안인증서 → 저희가 처리합니다",
        "   ※ 비밀번호는 알려주지 않으셔도 됩니다. 권한 초대만으로 다 됩니다.",
        "",
        "■ 저희가 알아서 하는 것 (신경 쓰지 않으셔도 됩니다)",
        "   · 홈페이지 제작·배포·보안인증서",
        "   · 글 작성, 검색엔진 등록 파일, 카톡 공유 명함 이미지",
        "   · 문의 추적과 매달 결과 리포트 발송",
        "   · 심의 제출용 점검표 자동 작성",
        "",
    ]

    lines += ["-" * 46, "[대표님 확인용 — 고객 발송 시 이 아래는 지울 것]", ""]
    lines.append(f"  고객이 직접 해야 할 것: {len(need)}건")
    lines.append(f"  도메인: {'미정 — site_url 수정 필요' if 'example.com' in cfg.get('site_url','') else '설정됨'}")
    lines.append(f"  문의 추적: {'꺼짐 — track_url 설정 필요' if not cfg.get('track_url') else '켜짐'}")
    lines.append(f"  소속사명 표기: {cfg.get('affiliation') or '(비표기)'} — 심의 승인 확인 필요")
    lines += [
        "",
        "  [계정 취급 원칙 — 지시서 5-1 / 12장]",
        "   절대 받지 말 것: 보험사 전산 계정, 금융 계정, 카톡 개인 비밀번호",
        "     → 사고 시 전적 책임. 자동 로그인은 구현 금지 항목.",
        "   권한 초대로 대체할 것: 카카오톡 채널, 구글 서치콘솔",
        "   비밀번호가 꼭 필요하면: 고객 PC에서 고객이 직접 로그인 (대행 보관 금지)",
    ]
    return "\n".join(lines), len(need)


def _kakao_buttons(url):
    """카톡 주소가 준비됐을 때만 버튼 HTML을 만든다 (자리표시자면 빈 문자열)."""
    ready = bool(url) and "xxxxxx" not in url
    def btn(cls, label):
        if not ready:
            return ""
        return (f'<a class="btn {cls}" href="{url}" target="_blank" rel="noopener" '
                f'data-ev="kakao">{label}</a>')
    return {
        "kakao_btn_contact": btn("btn-line", "카카오톡 상담"),
        # 하단 플로팅 바는 노란 칸이 비면 균형이 깨지므로, 카톡이 없을 땐 문의 폼으로 보낸다.
        "kakao_btn_float": btn("btn-kakao", "카톡으로 바로 묻기") or
                           '<a class="btn btn-kakao" href="#contact">문의 남기기</a>',
        "kakao_btn_article": btn("btn-kakao", "카톡으로 물어보기"),
    }


def _disclosure(cfg):
    """모든 페이지 맨 아래 의무 표시란. 업무광고에서 심의 담당이 먼저 찾는 항목을 한곳에 모은다."""
    notice = cfg.get("agent_notice") or (
        "보험설계사는 보험계약 체결 권한이 없으며, 보험계약의 체결 여부는 보험회사가 결정합니다. "
        "보험 계약 체결 전 상품설명서와 약관을 반드시 확인하시기 바랍니다.")
    # 샘플 값은 설명문 대신 자리 모양(○○)으로 보여 준다. 괄호 안에 괄호가 겹치면 심의 담당 눈에 엉성해 보인다.
    def v(key, shape):
        val = cfg.get(key) or ""
        return f"{shape} (샘플)" if not val or "샘플" in val else val
    rows = [
        f'소속 보험대리점: {v("agency_name", "○○보험대리점")} · 대리점 등록번호 {v("agency_reg_no", "제○○○○○○○○호")}',
        f'보험설계사 {cfg["name"]} · 협회 등록번호 {v("registration_no", "○○○○○○○○○○")}',
        notice,
        "기존 보험계약을 해지하고 새로운 보험계약을 체결하는 과정에서 질병 이력, 연령 증가 등으로 가입이 거절되거나 "
        "보험료가 인상될 수 있으며, 보장 제한 등 불이익이 발생할 수 있습니다.",
        f'준법감시인 확인필 {v("review_no", "제○○○○-○○○호")} · 유효기간 {v("review_valid", "○○○○.○○.○○ ~ ○○○○.○○.○○")}',
    ]
    return ('<div class="disclosure">' + "".join(f"<p>{r}</p>" for r in rows) +
            '<p><a href="{{root}}privacy.html">개인정보처리방침</a></p></div>')


def _reg_display(cfg):
    reg = cfg.get("registration_no") or ""
    return "○○○○○○○○○○ (샘플)" if not reg or "샘플" in reg else reg


def _identity(cfg, insured, root):
    """페이지마다 다른 두 자리: 호칭({{identity}})과 맨 아래 표시란({{disclosure}}).
    보험 이야기가 한 글자라도 있는 페이지 → '보험설계사' 호칭 + 모집종사자 의무 표시(금소법 22·26조, 보험업법 95조).
    없는 페이지(원칙) → 이름만 + 개인정보처리방침. 보험설계사라는 말 자체를 쓰지 않는다 — 클로징은 세무사와 현장에서(2026-10-31 대표님).
    풀 푸터는 보험 단어가 새어 들어갔을 때의 안전망이고, 그 페이지는 점검표에 [X]로 잡힌다.
    세무사법 쪽 안내('일반 정보, 자문 아님')는 템플릿 .legal 에 항상 있다 — 그쪽은 보험과 무관하게 지켜야 한다."""
    if insured:
        disclosure = _disclosure(cfg)
    else:
        disclosure = '<div class="disclosure"><p><a href="{{root}}privacy.html">개인정보처리방침</a></p></div>'
    # 운영자 입구: 모든 페이지 맨 아래 '업무 도구' 한 줄 → /tools/ (비밀번호 문, 검색 차단)
    disclosure = disclosure.replace("</div>", '<p><a href="{{root}}tools/">업무 도구</a></p>'
                                    # 제작사 표기: 고객 홈페이지마다 소통마케팅센터로 가는 링크 한 줄(영업 입구, 검색에도 보탬이 되게 nofollow 없음)
                                    f'<p class="maker">제작 <a href="{cfg.get("maker_url", "https://sotongmk.com")}" target="_blank" rel="noopener">'
                                    f'{cfg.get("maker_name", "소통마케팅센터")}</a></p></div>')
    return {"identity": f"보험설계사 {cfg['name']}" if insured else cfg["name"],
            "disclosure": disclosure.replace("{{root}}", root)}


# ---------- 업무 도구 페이지 조각 (선 아이콘·선 그리기 아트, 라이브러리 없음) ----------
_ICON_BOOK = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/>'
              '<path d="M4 20.5V5.5M8 7h8M8 11h6"/></svg>')
_ICON_FORM = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
              '<path d="M14 3v5h5M8 13h5M8 17h4"/><circle cx="17" cy="17" r="2.5"/><path d="m19 19 2 2"/></svg>')
_ICON_PLAN = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'
              '<path d="m3 8 6-4 6 6 6-4"/></svg>')
_ICON_OUT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8"/></svg>'
# 보고서 한 장 → 선이 흘러 → 슬라이드 두 장: 도구가 하는 일을 선으로 그린다(CSS가 획을 그린다)
_TFEAT_ART = ('<svg class="tfeat-art" viewBox="0 0 240 180" aria-hidden="true">'
              '<rect x="14" y="20" width="78" height="104" rx="8" pathLength="1"/>'
              '<path class="d2" d="M30 46h46M30 64h46M30 82h30M30 100h40" pathLength="1"/>'
              '<path class="d3" d="M100 72c24 0 24-26 48-26M100 72c24 0 24 30 52 30" pathLength="1"/>'
              '<rect class="d3" x="152" y="22" width="74" height="46" rx="6" pathLength="1"/>'
              '<rect class="d4" x="160" y="80" width="74" height="46" rx="6" pathLength="1"/>'
              '<path class="d4" d="M166 40h30M166 52h20M174 98h30M174 110h20" pathLength="1"/></svg>')


# ---------- /tools/ 글해줌 구독 문 (Cloudflare Pages _worker.js) ----------
# 업무 도구(법인 자료 정리·경영 플랜 비교·법령 서재·서식)는 글해줌 구독자만 쓴다. 홈페이지는 정적 파일이라 서버가 없으므로
# Cloudflare 가 요청을 먼저 받는 _worker.js 에서 /tools 만 글해줌 아이디·비밀번호를 묻고(서버 /api/tools/verify), 맞으면 30일 쿠키.
# 쿠키엔 마지막 확인 날짜가 들어 있어 날이 바뀌면 비밀번호 없이(TOOLS_API_KEY) 구독 상태를 다시 묻는다 → 해지·미납이면 하루 안에 멈춘다.
# 서버가 안 받아지면 닫힌다(fail-closed) — "구독 끊기면 작동 안 되게"의 뜻이 그것이다(2026-11-07 대표님).
# Pages 환경변수: TOOLS_API_KEY(글해줌 서버 .env 와 같은 값, secret) · TOOLS_OWNER_EMAIL(이 사이트 주인 계정, 비우면 구독자 누구나) · GEULHAEJUM_URL(기본 https://geulhaejum.kr)
# 두 모드(11/7 대표님 "당장은 비밀번호 하나로 통일, 팔 때 글해줌 연동" — 11/17 견본 비밀번호를 길게 바꿈, 값은 도구_비밀번호_bizsample.txt): TOOLS_PASSWORD 가 있으면 단순 비밀번호 문(견본·시연용), 없으면 글해줌 로그인 문(판매용).
# 팔 때는 그 사이트 Pages 에서 TOOLS_PASSWORD 를 지우고 TOOLS_API_KEY·TOOLS_OWNER_EMAIL 을 넣는다.
# 관리 화면(/admin) 들어가기도 이 문과 같은 글해줌 로그인이다(11/21 대표님 "원래 쓰던 비밀번호로") — 비밀값 GH_APP_ID·GH_APP_KEY(deploy.py admin)로
# 그 저장소 1시간 열쇠를 발급한다. 아래 admin() 주석.
WORKER_JS = r"""// 법인영업 홈페이지 — /tools/ 글해줌 구독 문. 나머지 주소는 정적 파일 그대로 (build.py 가 만든다).
// ponytail: 틀린 비밀번호 횟수 제한은 글해줌 서버 rate_limit(30/시간)에 맡긴다.
const GATE = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>업무 도구 · 글해줌 로그인</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f172a;color:#eef1f5;font-family:Pretendard,-apple-system,"Malgun Gothic",sans-serif}form{width:min(360px,90vw);background:#141c30;border:1px solid rgba(199,204,212,.18);border-radius:14px;padding:32px 28px;box-sizing:border-box}h1{font-size:18px;margin:0 0 6px}p{margin:0 0 18px;font-size:14px;color:#c7ccd4;line-height:1.6}input{width:100%;box-sizing:border-box;font-size:16px;padding:12px 14px;border-radius:8px;border:1px solid rgba(199,204,212,.3);background:#0f172a;color:#fff;margin-top:8px}button{width:100%;margin-top:12px;padding:12px;font-size:15px;font-weight:700;border:0;border-radius:8px;background:#eef1f5;color:#0f172a;cursor:pointer}.err{color:#f6b4b4;font-size:13px;min-height:18px;margin:8px 0 0}a{color:#c7ccd4;font-size:13px}</style></head>
<body><form method="post">{{form}}<button type="submit">들어가기</button><p class="err">{{msg}}</p><a href="/">홈으로</a></form></body></html>`;
const FORM_GEUL = `<h1>업무 도구 · 글해줌 로그인</h1><p>글해줌 구독 계정으로 들어갑니다. 한 번 들어오면 30일 동안 유지됩니다.</p><input type="email" name="email" autofocus autocomplete="username" placeholder="글해줌 이메일"><input type="password" name="pw" autocomplete="current-password" placeholder="비밀번호"><p style="margin:2px 0 12px;font-size:13px">비밀번호는 글해줌과 같습니다. <a href="https://geulhaejum.kr/forgot-password" target="_blank" rel="noopener" style="color:#93c5fd;white-space:nowrap">비밀번호를 잊으셨나요?</a></p>`;
const FORM_PW = `<h1>업무 도구</h1><p>이 홈페이지 주인 전용 공간입니다. 비밀번호를 넣어 주세요. 한 번 들어오면 30일 동안 유지됩니다.</p><input type="password" name="pw" autofocus autocomplete="current-password" placeholder="비밀번호">`;
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
// 견본처럼 비밀번호 문인 곳에서 무료 체험판으로 보내는 한 줄 — Pages 변수 TOOLS_TRIAL_URL 이 있는 사이트만(고객 사이트엔 안 넣는다, 11/20)
const trialLink = env => env.TOOLS_TRIAL_URL ? `<p style="margin:12px 0 0"><a href="${esc(env.TOOLS_TRIAL_URL)}" style="color:#fde68a;font-weight:700;font-size:14px">비밀번호가 없으신가요? 무료로 체험해 보기 →</a></p>` : '';

// 무료 체험 문(11/20 대표님 "이름·전화·동의만 받고 2번까지"): 폼은 신청 서버(car-track /trial)로 바로 간다 — 그래야 서버가 진짜 손님 IP 로
// 도배를 막는다. 서버가 보관·텔레그램·노션 뒤 10분짜리 입장표(t)를 붙여 /tools/enter 로 돌려보내면 여기서 확인하고 7일 쿠키.
// Pages 비밀값 TOOLS_TRIAL_SECRET = car-track 비밀값 TRIAL_SECRET (같은 값). 체험판 표시·2건 제한은 trial.js(build.py 가 tools_trial 세대에만 붙임).
const TRIAL_MSG = { form: '성함·휴대폰 번호·동의를 확인해 주세요.', many: '잠시 뒤 다시 시도해 주세요.', expired: '입장표가 지났습니다. 다시 한 번 눌러 주세요.' };
async function hmac(key, msg) {
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return [...new Uint8Array(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(msg)))].map(x => x.toString(16).padStart(2, '0')).join('');
}
function trialGate(env, url, msg) {
  const track = (env.TRIAL_TRACK_URL || 'https://car-track.choikiho20.workers.dev').replace(/\/$/, '');
  const hid = [['site', url.host], ...['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'].map(k => [k, url.searchParams.get(k) || ''])]
    .map(([k, v]) => `<input type="hidden" name="${k}" value="${esc(v.slice(0, 100))}">`).join('');
  const form = `<style>.ck{display:flex;gap:8px;align-items:flex-start;margin:12px 0 0;font-size:13px;color:#c7ccd4;line-height:1.5}.ck input{width:auto;margin:3px 0 0}</style>`
    + `<h1>업무 도구 무료 체험</h1><p>기업 보고서 PDF를 <b>2건까지</b> 직접 넣어 보실 수 있습니다. 넣은 보고서는 이 기기 안에서만 처리되고 서버로 가지 않습니다.</p>`
    + `<input name="name" required maxlength="20" autocomplete="name" placeholder="성함"><input name="phone" type="tel" required inputmode="tel" maxlength="20" autocomplete="tel" placeholder="휴대폰 번호">`
    + `<label class="ck"><input type="checkbox" name="consent" required><span>개인정보 수집·이용 동의(필수) — 성함·휴대폰 번호를 체험 확인과 상담 전화에만 쓰고 90일 뒤 지웁니다. <a href="https://sotong-corp.pages.dev/privacy" target="_blank" rel="noopener">자세히</a></span></label>`
    + `<input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">${hid}`
    + `<p style="margin:12px 0 0;font-size:13px">저장한 PPT에는 장마다 「체험판」 표시가 들어가 실제 고객 미팅에는 쓸 수 없습니다.</p>`;
  const page = GATE.replace('<form method="post">', () => `<form method="post" action="${track}/trial">`).replace('{{form}}', () => form)
    .replace('{{msg}}', () => esc(msg)).replace('>들어가기<', '>무료 체험 시작<');
  return new Response(page, { status: 401, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...GATE_SEC,
    // form-action 은 서버가 돌려보내는 길(303 → 이 사이트 /tools/enter)에도 적용된다 — 'self' 가 없으면 크롬이 되돌아오는 길을 막는다(11/20 실물 시험)
    'Content-Security-Policy': `default-src 'none'; style-src 'unsafe-inline'; form-action 'self' ${new URL(track).origin}; base-uri 'none'; frame-ancestors 'none'` } });
}

async function sha(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map(x => x.toString(16).padStart(2, '0')).join('');
}
const today = () => Math.floor(Date.now() / 86400000);
// 글해줌 서버에 묻는다. password 가 있으면 로그인, 없으면 key 로 구독 상태만.
async function ask(env, email, password) {
  if (!env.TOOLS_API_KEY) return { ok: false, reason: '설정이 아직 안 됐습니다(TOOLS_API_KEY). 운영자에게 문의하세요.' };
  if (!isOwner(env, email)) return { ok: false, reason: '이 홈페이지에 연결된 글해줌 계정이 아닙니다.' };
  try {
    const r = await fetch((env.GEULHAEJUM_URL || 'https://geulhaejum.kr') + '/api/tools/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(password ? { email, password } : { email, key: env.TOOLS_API_KEY }) });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok && j.ok === true, reason: j.reason || '글해줌 서버가 응답하지 않습니다.' };
  } catch (e) { return { ok: false, reason: '글해줌 서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.' }; }
}
// 서명에 사이트 주소(host)를 넣는다: 설계사 사이트마다 같은 TOOLS_API_KEY 를 쓰므로, 넣지 않으면 A 사이트 쿠키가 B 사이트에서 통한다 (11/13 보안검토)
const sign = (env, host, email, day, tag = 'corp-tools-v3') => sha(tag + ':' + env.TOOLS_API_KEY + ':' + host + ':' + email + ':' + day);
const isOwner = (env, email) => !env.TOOLS_OWNER_EMAIL || email === env.TOOLS_OWNER_EMAIL.trim().toLowerCase();
// 문 화면은 일꾼이 직접 만들어 _headers 가 안 붙는다 → 보안 머리글을 여기서 붙인다(스크립트 없음, 스타일만 안에).
const GATE_SEC = {
  'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains', 'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY', 'Referrer-Policy': 'strict-origin-when-cross-origin', 'X-Robots-Tag': 'noindex, nofollow' };
function gate(msg, status, form = FORM_GEUL) {
  return new Response(GATE.replace('{{form}}', form).replace('{{msg}}', msg), { status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...GATE_SEC } });
}
const cookie = (email, day, sig) => `tools_auth=${encodeURIComponent(email)}|${day}|${sig}; Path=/tools; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax`;
// 비밀번호 대입 막기(11/17): 같은 곳(IP)에서 10분에 5번 틀리면 10분 잠금. 일꾼(isolate) 메모리라 완벽하진 않지만
// 한 곳에서 몰아치는 대입은 여기서 멈춘다. 근본은 긴 비밀번호 — 견본 비밀번호는 도구_비밀번호_bizsample.txt.
const FAILS = new Map(), WINDOW = 600000, MAX_FAILS = 5;
const blocked = ip => { const r = FAILS.get(ip); return !!r && Date.now() - r[1] < WINDOW && r[0] >= MAX_FAILS; };
function failed(ip) {
  const r = FAILS.get(ip);
  if (!r || Date.now() - r[1] >= WINDOW) FAILS.set(ip, [1, Date.now()]); else r[0]++;
  if (FAILS.size > 5000) FAILS.clear();
}
const TOO_MANY = '비밀번호를 여러 번 틀려 10분 동안 잠겼습니다. 잠시 뒤 다시 해 주세요.';

// ---- 관리 화면(/admin) 들어가기 = 도구 문과 같은 글해줌 로그인 (11/21 대표님 "원래 쓰던 비밀번호로 계속") ----
// 비밀번호를 따로 두지 않는다. 글해줌 로그인이 맞고 이 사이트 주인 계정(TOOLS_OWNER_EMAIL — 관리 화면엔 '구독자 누구나'가 없다)이면
// 글해줌 GitHub 앱(JWT RS256)으로 이 저장소만·contents write 1시간 열쇠를 발급해 화면에 준다. 사람이 만드는 토큰(PAT)·잠긴 열쇠 파일이 없다.
// 30일 쿠키(admin_auth, Path=/admin, HttpOnly)로는 비밀번호 없이 열쇠만 다시 받고, 날이 바뀌면 구독을 조용히 다시 확인한다(도구 문과 같음).
// Pages 비밀값: GH_APP_ID · GH_APP_KEY(앱 비밀키 PKCS#8 DER base64 한 줄 — deploy.py admin/login 이 넣음). 견본(ADMIN_REPO 없음)엔 이 문이 없다.
// 앱 비밀키는 글해줌 서버와 각 세대 Pages 두 곳에 있다 — 새면 GitHub 앱에서 키를 다시 만들고 deploy.py admin all.
// ADMIN_REPO 는 Actions 가 GitHub 에서 받는 저장소 이름(GITHUB_REPOSITORY)으로 고정된다(build.py admin_repo_of) — 고객이 config 에 남의 저장소를 적어도 그 열쇠는 안 나온다(11/21 보안 검토).
const ADMIN_REPO = __ADMIN_REPO__;
const json = (o, status, extra = {}) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...GATE_SEC, ...extra } });
const b64url = u => btoa(String.fromCharCode(...u)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
async function appToken(env) {
  const now = Math.floor(Date.now() / 1000), enc = s => b64url(new TextEncoder().encode(s));
  const head = enc(JSON.stringify({ alg: 'RS256', typ: 'JWT' })) + '.' + enc(JSON.stringify({ iat: now - 60, exp: now + 540, iss: String(env.GH_APP_ID) }));
  const key = await crypto.subtle.importKey('pkcs8', Uint8Array.from(atob(env.GH_APP_KEY), c => c.charCodeAt(0)), { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
  const jwt = head + '.' + b64url(new Uint8Array(await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(head))));
  const H = { Authorization: 'Bearer ' + jwt, Accept: 'application/vnd.github+json', 'User-Agent': 'sotong-apt-admin', 'X-GitHub-Api-Version': '2022-11-28' };
  const inst = await (await fetch(`https://api.github.com/repos/${ADMIN_REPO}/installation`, { headers: H })).json().catch(() => ({}));
  if (!inst.id) throw new Error('이 홈페이지에 글해줌 앱이 아직 연결되지 않았습니다. 운영자에게 문의하세요.');
  const r = await fetch(`https://api.github.com/app/installations/${inst.id}/access_tokens`, { method: 'POST', headers: H,
    body: JSON.stringify({ repositories: [ADMIN_REPO.split('/')[1]], permissions: { contents: 'write' } }) });
  const j = await r.json().catch(() => ({}));
  if (!j.token) throw new Error('홈페이지 열쇠를 받지 못했습니다(' + r.status + '). 잠시 뒤 다시 해 주세요.');
  return { token: j.token, exp: j.expires_at };
}
const acookie = (email, day, sig, age = 2592000) => `admin_auth=${encodeURIComponent(email)}|${day}|${sig}; Path=/admin; Max-Age=${age}; HttpOnly; Secure; SameSite=Strict`;
// 표시 쿠키(비밀값 없음, 화면 JS 가 읽는다): 있을 때만 화면이 /admin/token 재발급을 시도한다 — 쿠키 없는 첫 방문에 401 콘솔 오류가 안 남게(11/21 실측)
const amark = (age = 2592000) => `admin_has=1; Path=/admin; Max-Age=${age}; Secure; SameSite=Strict`;
const withCookies = (res, ...cs) => { for (const c of cs) res.headers.append('Set-Cookie', c); return res; };
async function admin(request, env, url, ip) {
  if (!ADMIN_REPO) return json({ reason: '견본에는 관리 화면 로그인이 없습니다.' }, 404);
  if (request.method !== 'POST') return json({ reason: 'POST' }, 405);
  const sfs = request.headers.get('Sec-Fetch-Site');
  if (sfs && sfs !== 'same-origin') return json({ reason: '다른 사이트에서는 들어올 수 없습니다.' }, 403);
  if (url.pathname === '/admin/logout') return withCookies(json({ ok: true }, 200), acookie('', 0, '', 0), amark(0));
  if (!env.TOOLS_OWNER_EMAIL) return json({ reason: '이 홈페이지에 연결된 글해줌 계정이 아직 지정되지 않았습니다. 운영자에게 문의하세요.' }, 401);
  if (!env.GH_APP_ID || !env.GH_APP_KEY) return json({ reason: '설정이 아직 안 됐습니다(GH_APP_KEY). 운영자에게 문의하세요.' }, 401);
  let email;
  if (url.pathname === '/admin/login') {
    if (blocked(ip)) return json({ reason: TOO_MANY }, 429);
    const b = await request.json().catch(() => ({}));
    email = String(b.email || '').trim().toLowerCase();
    const pw = String(b.pw || '');
    if (!email || !pw) return json({ reason: '이메일과 비밀번호를 넣어 주세요.' }, 401);
    const v = await ask(env, email, pw);
    if (!v.ok) { failed(ip); return json({ reason: v.reason }, 401); }
  } else if (url.pathname === '/admin/token') {   // 30일 쿠키로 열쇠만 재발급 — 날이 바뀌면 구독을 조용히 다시 확인
    const m = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)admin_auth=([^|;]+)\|(\d+)\|([a-f0-9]+)/);
    if (!m) return json({ reason: '다시 들어가 주세요.' }, 401);
    email = decodeURIComponent(m[1]);
    const day = +m[2];
    if (!isOwner(env, email) || m[3] !== await sign(env, url.host, email, day, 'corp-admin-v1')) return json({ reason: '다시 들어가 주세요.' }, 401);
    if (day !== today()) { const v = await ask(env, email, ''); if (!v.ok) return json({ reason: v.reason }, 401); }
  } else return json({ reason: '없는 주소' }, 404);
  try {
    const t = await appToken(env);
    return withCookies(json(t, 200), acookie(email, today(), await sign(env, url.host, email, today(), 'corp-admin-v1')), amark());
  } catch (e) { return json({ reason: e.message }, 502); }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // www.주소 → 점 없는 주소로 301 — 검색엔진·AI 에 주소를 하나로 모은다
    if (url.hostname.startsWith('www.')) { url.hostname = url.hostname.slice(4); return Response.redirect(url.toString(), 301); }
    // 옛 임시 주소(<프로젝트>.pages.dev) → 정식 주소로 301. 옛 링크로 온 손님 문의도 들어가고(문의 서버는 보낸 주소 = 사이트 이름만 받는다),
    // 검색엔진엔 주소가 하나. 배포마다 생기는 미리보기 주소(<해시>.<프로젝트>.pages.dev)는 그대로. HOME 은 build.py 가 정식 주소일 때만 채운다.
    const HOME = __HOME__;
    if (HOME && /^[^.]+\.pages\.dev$/.test(url.hostname)) { url.hostname = HOME; return Response.redirect(url.toString(), 301); }
    const ip = request.headers.get('CF-Connecting-IP') || 'local';
    if (url.pathname.startsWith('/admin/')) return admin(request, env, url, ip);   // 관리 화면 들어가기(위 admin 주석) — /admin 화면 자체는 정적 파일
    if (!url.pathname.startsWith('/tools')) return env.ASSETS.fetch(request);
    if (env.TOOLS_TRIAL_SECRET) {                       // 무료 체험 세대(위 trialGate 주석). 정식·견본 세대엔 이 비밀값이 없다.
      const tok = await sha('corp-trial-v1:' + env.TOOLS_TRIAL_SECRET + ':' + url.host);
      if (url.pathname === '/tools/enter') {
        const [exp, sig] = String(url.searchParams.get('t') || '').split('.');
        if (+exp > Date.now() && sig && sig === await hmac(env.TOOLS_TRIAL_SECRET, url.host + '|' + exp))
          return new Response(null, { status: 303, headers: { 'Location': '/tools/corp/',
            'Set-Cookie': `tools_auth=${tok}; Path=/tools; Max-Age=604800; HttpOnly; Secure; SameSite=Lax` } });
        return trialGate(env, url, TRIAL_MSG.expired);
      }
      const c = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)tools_auth=([a-f0-9]+)(?:;|$)/);
      return c && c[1] === tok ? env.ASSETS.fetch(request) : trialGate(env, url, TRIAL_MSG[url.searchParams.get('e')] || '');
    }
    if (env.TOOLS_PASSWORD) {                           // 단순 비밀번호 문(견본·시연). 팔 때는 이 변수를 지운다.
      const tok = await sha('corp-tools-v1:' + env.TOOLS_PASSWORD);
      const FORM_PW_T = FORM_PW + trialLink(env);
      if (request.method === 'POST') {
        if (blocked(ip)) return gate(TOO_MANY, 429, FORM_PW_T);
        const form = await request.formData();
        if (String(form.get('pw') || '') !== env.TOOLS_PASSWORD) { failed(ip); return gate('비밀번호가 틀렸습니다.', 401, FORM_PW_T); }
        return new Response(null, { status: 303, headers: {
          'Location': url.pathname.endsWith('/') || url.pathname.endsWith('.html') ? url.pathname : '/tools/',
          'Set-Cookie': `tools_auth=${tok}; Path=/tools; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax` } });
      }
      const c = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)tools_auth=([a-f0-9]+)(?:;|$)/);
      return c && c[1] === tok ? env.ASSETS.fetch(request) : gate('', 401, FORM_PW_T);
    }
    if (request.method === 'POST') {
      if (blocked(ip)) return gate(TOO_MANY, 429);
      const form = await request.formData();
      const email = String(form.get('email') || '').trim().toLowerCase();
      const pw = String(form.get('pw') || '');
      if (!email || !pw) return gate('이메일과 비밀번호를 넣어 주세요.', 401);   // 빈 비밀번호가 key 재확인 경로로 새지 않게(11/7 보안검토)
      const v = await ask(env, email, pw);
      if (!v.ok) { failed(ip); return gate(v.reason, 401); }
      const day = today();
      return new Response(null, { status: 303, headers: {
        'Location': url.pathname.endsWith('/') || url.pathname.endsWith('.html') ? url.pathname : '/tools/',
        'Set-Cookie': cookie(email, day, await sign(env, url.host, email, day)) } });
    }
    const m = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)tools_auth=([^|;]+)\|(\d+)\|([a-f0-9]+)/);
    if (m && env.TOOLS_API_KEY) {
      const email = decodeURIComponent(m[1]), day = +m[2];
      if (isOwner(env, email) && m[3] === await sign(env, url.host, email, day)) {   // 소유자 확인은 쿠키 경로에서도 (TOOLS_OWNER_EMAIL 을 나중에 넣어도 옛 쿠키가 못 들어오게)
        if (day === today()) return env.ASSETS.fetch(request);
        const v = await ask(env, email, '');           // 날이 바뀜 → 구독이 아직 살아 있나 조용히 다시 확인
        if (v.ok) {
          const res = await env.ASSETS.fetch(request);
          const out = new Response(res.body, res);
          out.headers.append('Set-Cookie', cookie(email, today(), await sign(env, url.host, email, today())));
          return out;
        }
        return gate(v.reason, 401);
      }
    }
    return gate('', 401);
  }
};
"""


# ---------- 렌더 ----------
# 도구 코드 보호 1단계(2026-11-08 대표님 "복제품 금방 나오면 재미없다"): dist 에 들어가는 도구 JS 를 esbuild 로 압축·변수명 뒤섞기.
# 원본 법인도구/web 은 그대로. 압축본 맨 앞 한 줄이 저작권 배너(= 워터마크, 화면엔 안 보임, 소스를 열어야 보임) + 빌드 서명(원본 해시 12자).
# 2단계(서버로 산식 이전)는 유료 고객 뒤 — 올인원_도구_구상·계획.md 참고.
TOOLS_BANNER = "/*! (c) 2026 소통마케팅센터 · 글해줌 geulhaejum.kr · 법인영업 업무 도구 · 무단 복제·배포·역설계 금지 · build {date} {sig} · TR-{tid} */"


def _minify_tools(root, tid):
    """root 아래 .js/.mjs 를 제자리에서 압축한다. esbuild 가 없으면 빌드를 멈춘다(보호가 조용히 꺼지면 안 되니까)."""
    import subprocess
    files = sorted(p for p in root.rglob("*") if p.suffix in (".js", ".mjs"))
    sig = hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()[:12]
    banner = TOOLS_BANNER.format(date=date.today().isoformat(), sig=sig, tid=tid)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("npx 가 없어 도구 코드를 압축할 수 없다(node 설치 필요). 압축 없이 배포하지 않는다.")
    r = subprocess.run([npx, "--yes", "esbuild@0.28.2", "--minify", "--target=es2022", "--charset=utf8", "--legal-comments=none",
                        f"--banner:js={banner}", f"--outdir={root}", f"--outbase={root}", "--allow-overwrite", "--log-level=warning",
                        *map(str, files)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit("도구 코드 압축 실패:\n" + (r.stderr or r.stdout))
    return len(files), sig


def _seo_tool_pages(root, base, site):
    """도구 페이지(법인도구/web 복사본)에 canonical·JSON-LD·설명을 붙인다. 원본 54쪽은 손대지 않고 복사할 때마다 자동."""
    for p in root.rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        rel = p.relative_to(root).as_posix()
        # Cloudflare Pages 는 .html 을 떼고 index 는 폴더 주소로 넘긴다 — 최종 주소를 canonical 로.
        url = base + re.sub(r"(?<![^/])index$", "", rel[:-5])
        title = html.unescape(re.search(r"<title>(.*?)</title>", h, re.S).group(1).strip())
        add = ""
        m = re.search(r'<meta name="description" content="([^"]*)"', h)
        desc = html.unescape(m.group(1)) if m else ""
        if len(desc) < 20:   # 설명이 없는 3쪽(도구 첫 화면·서재 목차·서식)은 첫 안내 문단에서 딴다
            lead = re.search(r'<p class="lead">(.*?)</p>', h, re.S) or re.search(r"<main.*?<p[^>]*>(.*?)</p>", h, re.S)
            desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(lead.group(1)))).strip()[:150]
            add += f'<meta name="description" content="{html.escape(desc)}">'
        if 'rel="canonical"' not in h:
            add += f'<link rel="canonical" href="{url}">'
        if "application/ld+json" not in h:
            add += '<script type="application/ld+json">' + json.dumps({
                "@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
                "url": url, "inLanguage": "ko", "isPartOf": {"@type": "WebSite", "url": f"{site}/"},
            }, ensure_ascii=False) + "</script>"
        if add:
            p.write_text(h.replace("</title>", "</title>" + add, 1), encoding="utf-8")


def llms_txt(cfg, site, posts):
    """AI 검색이 JS 없이 한 번에 읽는 요약본. 화면·JSON-LD 와 같은 값에서 나온다(상호·지역·전화 통일). 자동차 단지와 같은 틀."""
    nl = "\n"
    return f"""# {cfg['region']} 법인 경영 컨설턴트 {cfg['name']}

> {cfg['tagline']}

## 기본 정보
- 이름: {cfg['name']} (법인 경영 컨설턴트 · 재무 구조·승계 설계)
- 활동 지역: {cfg.get('region_official', cfg['region'])}
- 전화: {cfg['phone']}
- 홈페이지: {site}/
- 세금 신고·법률 서류처럼 자격이 필요한 일은 세무사·변호사 등 해당 전문가가 수행합니다.

## 하는 일
{nl.join(f"- {c}" for c in cfg.get('career', []))}

## 자주 묻는 질문
{nl.join(f"- {f['q']} — {f['a']}" for f in cfg.get('faq', []))}

## 정리한 글
{nl.join(f"- [{p['title']}]({site}/posts/{p['slug']}) ({p.get('date', '')}): {p.get('description', '')}" for p in posts)}

## 채널
{nl.join(f"- {c['name']}: {c['url']}" for c in cfg.get('channels', [])) or '- (아직 없음)'}
"""


def write_favicon(cfg):
    """이름 첫 글자 파비콘. 브라우저 탭·검색 결과 옆에 나온다."""
    ch = html.escape(cfg["name"][:1])
    (DIST / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="10" fill="#0f172a"/>'
        f'<text x="24" y="33" font-size="26" font-weight="700" text-anchor="middle" fill="#fff" font-family="sans-serif">{ch}</text></svg>',
        encoding="utf-8")


def copy_indexnow_key():
    """IndexNow 키(32자리 hex.txt, 내용=파일명). 없으면 세대 폴더에 하나 만들고 dist 로 복사.
    deploy.py 가 올린 뒤 이 키로 빙·네이버·얀덱스 등에 한 번에 알린다(임시 주소는 noindex 라 건너뜀)."""
    keys = [p for p in ROOT.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}\.txt", p.name)]
    if not keys:
        k = secrets.token_hex(16)
        (ROOT / f"{k}.txt").write_text(k, encoding="utf-8")
        keys = [ROOT / f"{k}.txt"]
    shutil.copy2(keys[0], DIST / keys[0].name)


# 보안 머리글 A+ — 두 단지 공용 부품 engine/sec_headers.py 가 쓴다. 여기는 법인 도구가 실제로 부르는 바깥 주소만:
# PDF 읽기(pdf.js)·압축(jszip)=cdnjs, PPT(pptxgenjs)·글자 인식(tesseract)·영상(mediabunny)=jsdelivr,
# 글자 인식 언어 자료=tessdata.projectnaptha.com, 음성=Google TTS, 법령 감시=geulhaejum.kr. 새 바깥 자원을 붙이면 여기에 그 주소만 더한다.
SEC_SCRIPT = ("https://cdn.jsdelivr.net/npm/ https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/ "
              "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/ "
              "https://static.cloudflareinsights.com/")   # Pages 방문 통계(Web Analytics)가 페이지에 끼워 넣는 beacon — 막히면 콘솔 오류·통계 0(문진 11/20)
SEC_CONNECT = ("https://geulhaejum.kr https://texttospeech.googleapis.com https://cdn.jsdelivr.net "
               "https://cdnjs.cloudflare.com https://tessdata.projectnaptha.com https://cloudflareinsights.com")


def write_sec_headers(cfg):
    sys.path.insert(0, str(ENGINE.parent))
    import sec_headers
    track = re.match(r"https?://[^/]+", cfg.get("track_url") or "")
    return sec_headers.write(
        DIST, script=SEC_SCRIPT, wasm=True, worker=True, media="blob: data:",
        frame="https://www.youtube-nocookie.com",   # 따라 하기 영상 창(법인도구/web/howto.js, 11/18)
        style="https://fonts.googleapis.com https://cdn.jsdelivr.net", font="data: https://fonts.gstatic.com https://cdn.jsdelivr.net",
        connect="blob: data: " + SEC_CONNECT + (" " + track.group(0) if track else ""),
        admin=("admin.html",), admin_connect=track.group(0) if track else "")   # 관리 화면은 GitHub API·문의 서버만(경로별 예외)


def admin_repo_of(cfg):
    """관리 화면·일꾼에 들어가는 저장소 이름(owner/name). config 는 고객(관리 화면 열쇠)이 고칠 수 있는 파일이라, Actions 에서는
    GitHub 이 주는 GITHUB_REPOSITORY(고객이 못 바꾸는 값)로 고정하고 config 가 다르면 짓지 않는다 — 남의 저장소 이름을 적어 그 저장소
    열쇠를 받아 가는 길을 막는다(11/21 보안 검토). 이 PC 미리보기만 config 값."""
    repo = (cfg.get("admin_repo") or "").strip()
    if repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit(f"config admin_repo 는 owner/name 모양이어야 합니다: {repo}")
    real = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if real and repo and repo != real:
        sys.exit(f"config admin_repo({repo})가 이 저장소({real})와 다릅니다 — 다른 저장소 열쇠는 발급하지 않습니다")
    return real or repo


def write_admin(cfg, site):
    """사장님 셀프 관리 화면(11/21, 자동차 단지 것을 법인에 맞춤). admin_repo 가 비어 있으면(판매 전 견본) 저장 안 되는 '견본 모드'.
    값만 바꾼다(config.json·content/*.md·assets/) — 화면은 그 저장소의 Actions 가 다시 짓는다.
    들어가기는 _worker.js 의 /admin/login(글해줌 로그인) — 비밀번호 파일(admin-key.json)은 없다(11/21)."""
    repo = admin_repo_of(cfg)
    (DIST / "admin.html").write_text(render((ENGINE / "templates" / "admin.html").read_text(encoding="utf-8"), {
        "name": html.escape(cfg["name"]), "site": site, "track": (cfg.get("track_url") or "").rstrip("/"),
        "repo": repo, "branch": cfg.get("admin_branch", "main"),
        "key": "corp_admin_" + re.sub(r"\W", "_", repo or site),
    }), encoding="utf-8")
    if not repo:
        keys = ("name", "region", "eyebrow", "tagline", "intro", "phone", "kakao_url", "channels", "hero_image")
        (DIST / "admin-demo.json").write_text(json.dumps({k: cfg.get(k) for k in keys}, ensure_ascii=False), encoding="utf-8")


def render(template, mapping):
    for k, v in mapping.items():
        template = template.replace("{{" + k + "}}", str(v))
    leftover = re.findall(r"{{\w+}}", template)
    if leftover:
        sys.exit(f"치환 안 된 자리표시자: {leftover}")
    return template


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    insurers = json.loads((ENGINE / "insurers.json").read_text(encoding="utf-8"))
    posts = sorted(
        (parse_post(p) for p in (ROOT / "content").glob("*.md")),
        key=lambda p: p.get("date", ""), reverse=True,
    )

    if DIST.exists():
        # dist 폴더 자체는 두고 속만 비운다. 미리보기 서버(http.server --directory dist)나 그 안에 선 셸이
        # 폴더를 잡고 있으면 rmtree(DIST)가 WinError 32로 죽고, 그 상태로 배포하면 빈 사이트가 올라간다(10/31 실제로 두 번).
        for child in DIST.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    (DIST / "posts").mkdir(parents=True)
    (DIST / "tools").mkdir()
    shutil.copytree(ENGINE / "assets", DIST / "assets")
    shutil.copytree(ROOT / "assets", DIST / "assets", dirs_exist_ok=True)   # 세대 것이 엔진 것을 덮는다

    tpl = lambda n: (ENGINE / "templates" / n).read_text(encoding="utf-8")
    phone_digits = re.sub(r"\D", "", cfg["phone"])
    site = cfg["site_url"].rstrip("/")

    # 카톡 명함 카드는 파일명에 내용 해시를 붙인다.
    # 이름이 그대로면 카카오·페이스북이 예전 이미지를 계속 보여줘서, 사진을 바꿔도 반영되지 않는다.
    og_src = ROOT / (cfg.get("og_image") or "assets/og-card.jpg")
    if og_src.exists():
        og_tag = hashlib.md5(og_src.read_bytes()).hexdigest()[:8]
        og_name = f"{og_src.stem}-{og_tag}.jpg"
        shutil.copy2(og_src, DIST / "assets" / og_name)
        og_image = f"{site}/assets/{og_name}"
    else:
        og_image = f"{site}/assets/og-card.jpg"

    common = {
        "name": cfg["name"],
        "region": cfg["region"],
        "region_official": cfg.get("region_official", cfg["region"]),
        "eyebrow": cfg.get("eyebrow") or f"{cfg['region']} 법인 경영 컨설턴트",
        "years": cfg["years"],
        "tagline": cfg["tagline"],
        "phone": cfg["phone"],
        "phone_link": f"tel:{phone_digits}",
        "kakao_url": cfg["kakao_url"],
        # 카톡 주소가 아직 자리표시자면 버튼을 아예 내보내지 않는다. 죽은 링크를 보여주는 것보다 없는 편이 낫다.
        **_kakao_buttons(cfg.get("kakao_url", "")),
        "site_url": site,
        "og_image": og_image,
        "track_url": cfg["track_url"],
        "site_id": re.sub(r"^https?://", "", site),
        "hero_image": cfg.get("hero_image", "assets/hero.svg"),
        "hero_cutout": cfg.get("hero_cutout") or cfg.get("hero_image", "assets/hero.svg"),
        # 가상 인물 샘플은 사진 밑에 그 사실을 적는다. 실제 고객 페이지에서는 config에서 비운다.
        "hero_caption": (f'<p class="hero-caption">{cfg["hero_caption"]}</p>'
                         if cfg.get("hero_caption") else ""),
        "hero_video": (
            f'<video class="hero-video" src="{cfg["hero_video"]}" autoplay loop muted playsinline aria-hidden="true"></video>'
            if cfg.get("hero_video") else ""
        ),
        "year": date.today().year,
        "updated": date.today().isoformat(),
        "reg_display": _reg_display(cfg),
        # 검색엔진 소유 확인 메타(구글·네이버·빙). 지우면 소유 확인이 풀린다. 다음은 robots.txt(daum_verification)
        "verification_meta": "".join(
            f'<meta name="{name}" content="{cfg[key]}">'
            for key, name in (("google_verification", "google-site-verification"),
                              ("naver_verification", "naver-site-verification"),
                              ("bing_verification", "msvalidate.01"))
            if cfg.get(key)
        ),
        "robots_meta": (
            '<meta name="robots" content="noindex, nofollow">'
            if any(h in site for h in ("pages.dev", "netlify.app", "vercel.app", "github.io", "example.com"))
            else ""
        ),
    }

    # 첫 화면·개인정보 페이지는 config의 '보이는 글'(의무 표시 값과 *_note 설명은 뺀 것)에 보험 이야기가 있는지로 정한다.
    # 소속 GA를 표기하면 그 자체가 보험 영업 광고라 같이 센다. 글은 아래 반복문에서 글마다 따로 본다.
    visible = {k: v for k, v in cfg.items()
               if k not in ("review_no", "review_valid", "agency_name", "agency_reg_no", "agent_notice", "registration_no")
               and not k.endswith("_note")}
    insured_index = (mentions_insurance(json.dumps(visible, ensure_ascii=False))
                     or bool(cfg.get("affiliation", "").strip()))
    full_pages = ["index.html (첫 화면·개인정보처리방침)"] if insured_index else []

    # 섹션 조립
    career_items = "".join(f"<li>{c}</li>" for c in cfg["career"])
    affiliation = f"<li>소속: {cfg['affiliation']}</li>" if cfg.get("affiliation") else ""
    # 상황 카드 → 해당 글로 연결. 오타로 죽은 링크가 조용히 배포되지 않게 slug를 검증한다.
    slugs = {p["slug"] for p in posts}
    def situation_card(s):
        body = f'<h3>{s["title"]}</h3><p>{s["desc"]}</p>'
        link = s.get("link")
        if not link:
            return f'<div class="card reveal">{body}</div>'
        if link not in slugs:
            sys.exit(f"상황 카드 '{s['title']}'의 link '{link}'에 해당하는 글이 content/에 없습니다. "
                     f"사용 가능: {sorted(slugs)}")
        label = s.get("link_label", "자세히 보기")
        return (f'<a class="card card-link reveal" href="posts/{link}.html">{body}'
                f'<span class="card-more">{label}</span></a>')
    situation_cards = "".join(situation_card(s) for s in cfg["situations"])

    # 청구 사례 카드. cases_are_samples가 켜져 있으면 화면에 "예시" 뱃지를 붙인다.
    # 예시를 실제 사례처럼 내보내는 게 이 섹션의 유일한 사고 경로라서, 끄는 걸 잊으면 티가 나게 둔다.
    # 카톡 화면은 방문자(고객) 휴대폰 시점: 고객 = 오른쪽 노란 말풍선, 설계사 = 왼쪽 흰 말풍선 + 사진·이름.
    # 설계사 얼굴이 대화 안에 보여야 '이 사람이 이렇게 답해 준다'가 전해진다. config의 who: me = 설계사.
    def kakao_msgs(chat):
        out, prev = [], None
        for m in chat:
            if m["who"] == "me":
                head = (f'<img class="km-avatar" src="{common["hero_image"]}" alt="">'
                        f'<span class="km-name">{cfg["name"]}</span>') if prev != "me" else ""
                out.append(f'<div class="km agent{" cont" if prev == "me" else ""}">{head}'
                           f'<div class="km-row"><p>{m["text"]}</p><time>{m["time"]}</time></div></div>')
            else:
                out.append(f'<div class="km cust"><div class="km-row"><time>{m["time"]}</time>'
                           f'<p>{m["text"]}</p></div></div>')
            prev = m["who"]
        return "".join(out)

    def case_card(c):
        sample = ('<span class="case-tag case-sample">예시</span>'
                  if cfg.get("cases_are_samples") else "")
        chat = c.get("chat", [])
        chat_box = (
            '<div class="kakao" aria-label="카카오톡 상담 화면 재구성">'
            f'<div class="kakao-bar"><span aria-hidden="true">‹</span><b>{cfg["name"]}</b><span aria-hidden="true">≡</span></div>'
            f'<div class="kakao-body">{kakao_msgs(chat)}</div></div>'
        ) if chat else ""
        note = ("위 대화는 실제 상담 내용을 바탕으로 다시 구성한 화면이며, "
                "고객 동의를 받고 개인정보는 지웠습니다.") if chat else ""
        return (
            '<article class="case">'
            f'<div class="case-head"><span class="case-tag">{c["tag"]}</span>{sample}'
            f'<h3>{c["title"]}</h3></div>'
            f'{chat_box}'
            '<dl>'
            f'<dt>어떤 상황이었나</dt><dd>{c["situation"]}</dd>'
            f'<dt>어떻게 했나</dt><dd>{c["result"]}</dd>'
            '</dl>'
            f'<p class="case-note">{note}</p>'
            '</article>'
        )
    cases = cfg.get("cases", [])
    # 세로로 길게 쌓지 않고 좌우로 넘긴다. 라이브러리 없이 CSS scroll-snap — 손가락 스와이프는 브라우저가 처리.
    case_cards = (
        '<div class="slider reveal">'
        '<div class="cases" tabindex="0">' + "".join(case_card(c) for c in cases) + "</div>"
        '<div class="slider-nav"><button class="slider-btn" data-dir="-1" aria-label="이전 사례">←</button>'
        '<div class="dots">' + "".join(
            f'<button class="dot" aria-label="{i}번째 사례"></button>' for i in range(1, len(cases) + 1)
        ) + '</div><button class="slider-btn" data-dir="1" aria-label="다음 사례">→</button></div>'
        "</div>"
        if cases else ""
    )
    # 보험사 앱 아이콘. 실제 로고는 상표 문제로 쓰지 않고, 회사명 앞 두 글자를 아이콘처럼 보여 준다.
    def ins_mark(name):
        base = re.sub(r"(생명|화재|손해보험|손보|라이프|해상|보험|캐피탈)+$", "", name) or name
        return base if len(base) <= 3 else base[:2]
    link_group = lambda items: "".join(
        f'<a class="ins" href="{i["url"]}" target="_blank" rel="noopener nofollow">'
        f'<span class="ins-icon" aria-hidden="true">{i.get("mark") or ins_mark(i["name"])}</span>'
        f'<span class="ins-name">{i["name"]}</span></a>'
        for i in items
    )
    posts_list = "".join(
        f'<a class="post-row reveal" href="posts/{p["slug"]}.html">'
        f'<span class="post-date">{p.get("date", "")}</span>'
        f'<span class="post-title">{p["title"]}</span>'
        f'<span class="post-desc">{p.get("description", "")}</span></a>'
        for p in posts
    )
    # 소속 뱃지는 affiliation이 승인돼 채워져 있을 때만 붙인다.
    # 따로 하드코딩하면 심의 반려 시 affiliation만 비워도 뱃지에 회사명이 남아 롤백이 새어나간다.
    chip_list = list(cfg.get("chips", []))
    if cfg.get("affiliation", "").strip() and cfg.get("affiliation_short", "").strip():
        chip_list.insert(0, cfg["affiliation_short"].strip())
    chips = "".join(f"<span class='chip'>{c}</span>" for c in chip_list)
    # 원칙 아이콘: 선으로 그려지는 SVG(화면에 들어오면 CSS가 획을 그린다). 로티 파일 없이 같은 효과.
    icons = [
        '<rect x="6" y="4" width="20" height="25" rx="3"/><path d="M12 4V2h8v2"/><path d="m11 16 3.5 3.5L21 13"/>',
        '<path d="M16 2 4 7v8c0 7.5 5 12.5 12 15 7-2.5 12-7.5 12-15V7z"/><path d="m10.5 16 4 4 7.5-8"/>',
        '<path d="M4 6h24v15H14l-6 5v-5H4z"/><path d="M10 12h12M10 16h7"/>',
    ]
    principle_items = "".join(
        f'<div class="principle reveal"><svg class="p-icon" viewBox="0 0 32 32" aria-hidden="true">{icons[i % len(icons)]}</svg>'
        f'<h3>{p["title"]}</h3><p>{p["desc"]}</p></div>'
        for i, p in enumerate(cfg.get("principles", []))
    )
    badges = "".join(
        f'<span class="badge"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 1.5 12.6 7l6 .6-4.5 4 1.3 5.9L10 14.5l-5.4 3 1.3-5.9-4.5-4 6-.6z"/></svg>{b}</span>'
        for b in cfg.get("badges", [])
    )
    # 숫자 카드: 화면에는 최종값을 그대로 찍어 두고(검색·JS 꺼짐 대비) 스크립트가 0부터 다시 센다.
    stats = "".join(
        f'<div class="stat reveal"><b data-to="{s["value"]}" data-suffix="{s.get("suffix", "")}">'
        f'{s["value"]:,}<small>{s.get("suffix", "")}</small></b><span>{s["label"]}</span></div>'
        for s in cfg.get("stats", [])
    )
    stats_block = (
        f'<div class="stats">{stats}</div>'
        + ('<p class="stats-note">※ 샘플 페이지의 예시 자격·수치입니다. 실제 페이지에는 본인 기록만 들어갑니다.</p>'
           if cfg.get("credentials_are_samples") else "")
    ) if stats else ""
    process_steps = "".join(
        f'<div class="step reveal"><span class="step-no">{i}</span>'
        f'<div><h3>{s["title"]}</h3><p>{s["desc"]}</p></div></div>'
        for i, s in enumerate(cfg.get("process", []), 1)
    )
    faq_items = "".join(
        f'<details class="faq reveal"><summary>{f["q"]}</summary><p>{f["a"]}</p></details>'
        for f in cfg.get("faq", [])
    )
    # sameAs: 같은 사람의 다른 주소(블로그·인스타·유튜브·카톡 채널). 빈 주소·자리표시자 카톡은 뺀다 — 지어낸 주소는 넣지 않는다.
    same_as = [c["url"] for c in cfg.get("channels", []) if (c.get("url") or "").strip()]
    if cfg.get("kakao_url") and "xxxxxx" not in cfg["kakao_url"]:
        same_as.append(cfg["kakao_url"])
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "InsuranceAgency" if insured_index else "ProfessionalService",
        "name": f"보험설계사 {cfg['name']}" if insured_index else cfg["name"],
        "description": cfg["tagline"],
        "areaServed": [cfg["region"], cfg.get("region_official", cfg["region"])],
        "telephone": cfg["phone"],
        "url": site,
        **({"sameAs": same_as} if same_as else {}),
    }, ensure_ascii=False)
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in cfg.get("faq", [])
        ],
    }, ensure_ascii=False)

    index = render(tpl("index.html"), {
        **common,
        **_identity(cfg, insured_index, ""),
        "og_title": cfg.get("og_title") or f'{cfg["region"]} 법인 경영 컨설턴트 {cfg["name"]}',
        "og_description": cfg.get("og_description") or cfg["tagline"],
        "intro": cfg["intro"],
        "career_items": career_items + affiliation,
        "situation_cards": situation_cards,
        "case_cards": case_cards,
        "insurer_links_life": link_group(insurers["life"]),
        "insurer_links_general": link_group(insurers["general"]),
        "count_life": f'{len(insurers["life"])}곳',
        "count_general": f'{len(insurers["general"])}곳',
        "posts_list": posts_list,
        "chips": chips,
        "badges": badges,
        "stats_block": stats_block,
        "principle_items": principle_items,
        "process_steps": process_steps,
        "faq_items": faq_items,
        "jsonld": jsonld,
        "faq_jsonld": faq_jsonld,
    })
    (DIST / "index.html").write_text(index, encoding="utf-8")
    (DIST / "privacy.html").write_text(render(tpl("privacy.html"), {
        **common, **_identity(cfg, insured_index, ""),
        "collector": cfg["name"],
        "processor": "문의 접수 서버 운영 — 소통마케팅센터 (홈페이지 제작·관리 위탁)" if cfg.get("track_url") else "없음",
    }), encoding="utf-8")

    for p in posts:
        # 글에 보험 이야기가 있으면(제목·요약·본문) 그 글만 풀 푸터·'보험설계사' 호칭. 한 번 나와도 센다(4대보험 같은 사회보험은 제외).
        insured = mentions_insurance(" ".join((p["title"], p.get("description", ""), p["text"])))
        if insured:
            full_pages.append(f"posts/{p['slug']}.html")
        # 같은 고민으로 들어온 손님이 한 글만 읽고 나가지 않게, 최신 글 3편을 이어 붙인다.
        related = "".join(
            f'<li><a href="{o["slug"]}.html">{o["title"]}</a></li>'
            for o in [o for o in posts if o["slug"] != p["slug"]][:3])
        article_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": p["title"],
            "description": p.get("description", ""),
            "datePublished": p.get("date", ""),
            "dateModified": p.get("date", ""),
            "inLanguage": "ko",
            "keywords": p.get("keywords", ""),
            "mainEntityOfPage": f"{site}/posts/{p['slug']}",
            "image": og_image,
            "author": {"@type": "Person", "name": cfg["name"], **({"jobTitle": "보험설계사"} if insured else {}),
                       "areaServed": cfg["region"], "url": f"{site}/"},
            "publisher": {"@type": "Person", "name": cfg["name"], "url": f"{site}/"},
        }, ensure_ascii=False)
        page = render(tpl("post.html"), {
            **common,
            **_identity(cfg, insured, "../"),
            "author_note": (
                f'{cfg["region"]} · 협회 등록번호 {common["reg_display"]}<br>법인 대표님께 관련 법령과 제도를 조문 기준으로 '
                "정리해 드리고, 세무·법률 판단은 담당 전문가와 함께 하시도록 안내합니다. 글의 내용은 보험설계사 개인의 의견이며, "
                "계약 체결에 따른 이익 또는 손실은 보험계약자에게 귀속됩니다."
                if insured else
                f'{cfg["region"]} · 법인 경영 컨설턴트<br>가지급금·퇴직금·정관·승계를 대표님 회사의 숫자로 분석해 설계합니다. '
                "자격이 필요한 신고·서류는 함께 일하는 세무사·변호사가 맡습니다."),
            "title": p["title"],
            "description": p.get("description", ""),
            "date": p.get("date", ""),
            "slug": p["slug"],
            "content": p["html"],
            "related": related,
            "article_jsonld": article_jsonld,
        })
        (DIST / "posts" / f"{p['slug']}.html").write_text(page, encoding="utf-8")

    # 법인 자료 정리 도구(sotong-sites/법인도구/web)를 설계사 전용 /tools/corp/ 에 통째로 넣는다 (2026-10-30).
    # 브라우저 안에서만 도는 정적 파일이라 서버·로그인이 없다. 검색 차단은 /tools/ 와 같다(noindex + robots Disallow).
    tool_src = TOOLS
    tools_links = ""
    if not tool_src.exists():   # 도구 없이 올라가면 고객 사이트의 /tools 가 빈 문이 된다 — 조용히 넘기지 않는다
        sys.exit(f"업무 도구 원본이 없습니다: {tool_src}")
    if tool_src.exists():
        shutil.copytree(tool_src, DIST / "tools" / "corp")
        _seo_tool_pages(DIST / "tools" / "corp", f"{site}/tools/corp/", site)
        # 세대별 유출 추적 표식(11/17) — 방식은 비공개 저장소(법인도구/leak_trace.py)에만 있다. 없으면 빌드를 멈춘다.
        sys.path.insert(0, str(TOOLS.parent))
        import leak_trace
        tid = leak_trace.unit_id(ROOT)
        n_tr, n_zw = leak_trace.stamp(DIST / "tools" / "corp", tid)
        n_js, sig = _minify_tools(DIST / "tools" / "corp", tid)
        print(f"도구 코드 압축 {n_js}개 (서명 {sig}) · 추적 표식 코드 {n_tr}곳·화면 {n_zw}쪽")
        # 큰 카드 하나(도구) + 옆 카드 둘(법령 서재·서식). 템플릿 CSS 는 templates/tools.html 안에.
        tools_links += (
            '<section class="tfeat">'
            '<a class="tfeat-main reveal" href="corp/">'
            '<span class="tfeat-kicker">법인 자료 정리</span>'
            '<h2>보고서 PDF 하나 넣으면<br>한 장 입력표 · 계산표 4종 · 브리핑 16장</h2>'
            '<p>크레탑·나이스 보고서를 이 기기 안에서만 읽습니다. 숫자는 법령 산식으로 계산하고, 브리핑은 태블릿으로 넘기거나 PPT로 내려받습니다.</p>'
            '<span class="tfeat-cta">보고서 넣고 시작하기 →</span>' + _TFEAT_ART + '</a>'
            '<div class="tfeat-side">'
            '<a class="tcard reveal" href="corp/study/">' + _ICON_BOOK +
            '<b>법령 서재 49주제</b><span>재무·세무·노무·위험 대비·정관·인증·법무 7영역. 현행 조문 원문, 대표님이 자주 묻는 질문, 말하면 안 되는 선.</span>'
            '<span class="go">법령 서재 열기</span></a>'
            '<a class="tcard reveal" href="corp/sim/">' + _ICON_PLAN +
            '<b>경영 플랜 비교</b><span>보수·배당 비교 · 임원 퇴직금 설계 · 사내근로복지기금 설계. 숫자를 누르면 근거 조문이 바로 뜹니다.</span>'
            '<span class="go">비교 화면 열기</span></a>'
            '<a class="tcard reveal" href="corp/study/forms.html">' + _ICON_FORM +
            '<b>서식 찾기</b><span>시행규칙 별지 서식 1,375건을 이름으로 검색하고, 법령정보센터 공식 파일로 바로 갑니다.</span>'
            '<span class="go">서식 검색</span></a>'
            '</div></section>')
    def _mark(label):   # 바로가기 왼쪽 네모 글자. 로고는 상표 문제로 안 쓴다.
        for key, mark in (("법령", "법령"), ("국세", "국세"), ("금융", "금감"), ("등기", "등기"), ("중소", "중기")):
            if key in label:
                return mark
        return label[:2]
    for g in dict.fromkeys(l["group"] for l in cfg["tools_links"]):
        rows = "".join(
            f'<a class="tlink reveal" href="{l["url"]}" target="_blank" rel="noopener">'
            f'<span class="tlink-mark">{_mark(l["label"])}</span><b>{l["label"]}</b>{_ICON_OUT}</a>'
            for l in cfg["tools_links"] if l["group"] == g
        )
        tools_links += f'<section class="tgroup"><h2 class="sec-label">{g}</h2><div class="tlinks">{rows}</div></section>'
    (DIST / "tools" / "index.html").write_text(
        render(tpl("tools.html"), {**common, "disclosure": "", "tools_links": tools_links, "tools_jsonld": json.dumps({
            "@context": "https://schema.org", "@type": "CollectionPage", "name": f"업무 도구 — {cfg['name']}",
            "url": f"{site}/tools/", "inLanguage": "ko", "isPartOf": {"@type": "WebSite", "url": f"{site}/"},
        }, ensure_ascii=False)}), encoding="utf-8")
    (DIST / "404.html").write_text(render(tpl("404.html"), common), encoding="utf-8")
    # 임시 배포 주소는 색인을 막는다. 버릴 주소에 검색을 쌓으면 도메인 이전 때 그만큼 손해.
    staging = any(h in site for h in ("pages.dev", "netlify.app", "vercel.app", "github.io", "example.com"))
    # /tools/ 글해줌 구독 문 — Cloudflare Pages 가 dist/_worker.js 를 먼저 태운다. 설정은 WORKER_JS 위 주석.
    # 일꾼 코드에 들어가는 값 둘은 json.dumps(따옴표 포함)로 — 값이 어떻든 문자열 밖으로 못 나간다. 호스트는 모양까지 좁힌다(11/21 보안 검토)
    home = "" if staging else re.sub(r"^https?://", "", site).split("/")[0]
    if home and not re.fullmatch(r"[A-Za-z0-9.-]+", home):
        sys.exit(f"site_url 호스트 모양이 이상합니다: {home}")
    (DIST / "_worker.js").write_text(
        WORKER_JS.replace("__HOME__", json.dumps(home)).replace("__ADMIN_REPO__", json.dumps(admin_repo_of(cfg))), encoding="utf-8")

    # SEO: sitemap + robots (발행 시마다 자동 갱신)
    # Cloudflare Pages는 .html 주소를 확장자 없는 주소로 308 넘긴다. 검색엔진에는 최종 주소를 알려야 한다.
    urls = [f"{site}/"] + [f"{site}/posts/{p['slug']}" for p in posts]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
    (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (DIST / "llms.txt").write_text(llms_txt(cfg, site, posts), encoding="utf-8")
    copy_indexnow_key()
    write_favicon(cfg)
    if staging:
        # 링크 미리보기 봇(카톡 등)까지 막으면 공유 카드가 갱신되지 않는다. 검색 색인은 noindex 메타가 따로 막는다.
        (DIST / "robots.txt").write_text(
            "User-agent: kakaotalk-scrap\nAllow: /\n\n"
            "User-agent: facebookexternalhit\nAllow: /\n\n"
            "User-agent: *\nDisallow: /\n", encoding="utf-8")
    else:
        (DIST / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nDisallow: /tools/\nDisallow: /admin.html\nSitemap: {site}/sitemap.xml\n"
            + (f"#DaumWebMasterTool:{cfg['daum_verification']}\n" if cfg.get("daum_verification") else ""),  # 다음 웹마스터도구 소유 확인
            encoding="utf-8")

    # config.json도 화면에 그대로 노출되므로 글과 같은 기준으로 검사한다.
    # affiliation은 의도적 표기라 일반 스캔에서 빼고 아래 [!] 항목으로 따로 고지 —
    # 그래야 본문에 실수로 들어간 보험사명이 이 한 건에 묻히지 않는다.
    # *_note 는 운영자 메모라 화면에 안 나간다 — 검사에서 뺀다.
    scanned_cfg = {k: v for k, v in cfg.items()
                   if k not in ("affiliation", "affiliation_note", "affiliation_short") and not k.endswith("_note")}
    cfg_doc = {"label": "config.json", "text": json.dumps(scanned_cfg, ensure_ascii=False, indent=1)}
    checklist, ok = compliance_check(posts + [cfg_doc], insurers, cfg.get("affiliation", "").strip(), full_pages)
    # dist/에 두면 사이트와 함께 공개된다(누구나 /심의체크리스트.txt로 열람). 작업 폴더에만 둔다.
    (ROOT / "심의체크리스트.txt").write_text(checklist, encoding="utf-8")
    print(checklist)
    print()
    # 고객에게 요청할 준비물 안내 (배포물이 아니므로 dist/가 아닌 작업 폴더에 둔다)
    todo, todo_n = client_todo(cfg, ROOT, len(full_pages))
    (ROOT / "고객에게_보낼_안내.txt").write_text(todo, encoding="utf-8")
    if cfg.get("tools_trial"):   # 무료 체험 세대(11/20): 도구 모든 쪽에 체험판 띠·워터마크·보고서 2건 제한(engine/corp/trial.js)
        shutil.copy(ENGINE / "trial.js", DIST / "tools" / "trial.js")
        n_trial = 0
        for p in (DIST / "tools").rglob("*.html"):
            h = p.read_text(encoding="utf-8")
            if "/tools/trial.js" not in h:
                p.write_text(h.replace("</head>", '<script src="/tools/trial.js"></script></head>', 1), encoding="utf-8")
                n_trial += 1
        print(f"무료 체험판: 도구 {n_trial}쪽에 체험판 표시·2건 제한")
    write_admin(cfg, site)
    n_js, n_on = write_sec_headers(cfg)   # dist 를 다 지은 뒤 마지막에 — 페이지 안 코드 지문을 떠야 하므로
    print(f"보안 머리글: dist/_headers (페이지 안 스크립트 {n_js}개·인라인 이벤트 {n_on}개 지문 허용, 관리 화면 따로)")

    if not cfg["track_url"]:
        print("[경고] track_url이 비어 있어 문의 추적이 꺼진 상태로 빌드됨 (지시서 6장: 추적 없으면 3개월 안에 이탈)")
    if todo_n:
        print(f"[대기] 고객에게 받을 것 {todo_n}건 → 고객에게_보낼_안내.txt (카톡 붙여넣기용)")
    print(f"빌드 완료: dist/  (글 {len(posts)}편, 심의 자동점검 {'통과' if ok else '위반 있음 — 위 목록 확인'})")


if __name__ == "__main__":
    main()
