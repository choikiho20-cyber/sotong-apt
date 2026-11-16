# -*- coding: utf-8 -*-
"""자동차 영업사원 홈페이지 — 아파트 엔진 (시공사는 이 파일 하나).

  엔진  engine/car/       build·publish·화면 틀(templates)·공용 자산(style·track)·첫 글(content_starter)
  메이커 engine/car/makers/<이름>/   lineup.json(차종)·art/(차종 그림)·cars/(원본 차 이미지)
  세대  units/<영업사원>/   config.json·assets/(본인 사진·카톡 카드·출고 사진)·content/(글)·IndexNow 키

세대 폴더 + 엔진 + 메이커 -> 세대/dist/
부수 산출물: sitemap.xml, robots.txt, llms.txt, 404.html, IndexNow 키, 광고점검표.txt, 고객에게_보낼_안내.txt
검색 기준은 ~/.claude/skills/homepage-seo (audit.py FAIL 0) — 글 Article JSON-LD·sameAs·WebP·최종 수정일 포함
사용법: python build.py <세대 폴더>   (세대 폴더 안의 build.py 를 돌려도 같다)
"""
import hashlib
import json
import re
import secrets
import shutil
import sys
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote

import segno

ENGINE = Path(__file__).resolve().parent
ROOT = None      # 지금 짓는 세대 폴더 (use_unit 이 정한다)
DIST = None
MAKER = None     # 이 세대의 메이커 폴더 (main 이 config 의 lineup 으로 정한다)


def use_unit(path):
    global ROOT, DIST
    ROOT = Path(path).resolve()
    DIST = ROOT / "dist"


def src(rel):
    """화면에 쓰는 파일 경로(assets/...)가 실제로 어디 있는지 — 세대 것이 우선, 없으면 메이커·엔진 것.
    차종 그림(assets/art/)은 메이커 폴더에 한 벌만 둔다."""
    if rel.startswith("assets/art/") and MAKER:
        return MAKER / "art" / rel[len("assets/art/"):]
    if (ROOT / rel).exists() or not rel.startswith("assets/"):
        return ROOT / rel
    return ENGINE / rel

# 한글 Windows 콘솔(cp949)에서 점검표 출력이 깨지거나 죽지 않도록
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# 빌드 중에 모인 경고. 죽이지는 않되 화면에는 반드시 남긴다.
WARNINGS = []


# ---------- 미니 마크다운 변환 (의존성 없음) ----------
def safe_url(url):
    """주소는 http(s) 또는 같은 사이트 안 경로만. javascript: 같은 주소로 스크립트가 끼어드는 것을 막는다."""
    return url if re.match(r"https?://", url) or not re.match(r"[a-zA-Z][\w+.-]*:", url) else ""


def inline(text, slugs):
    # 글(AI 원고·관리 화면 입력)에 섞인 <script> 등은 글자로만 보이게 먼저 이스케이프한다.
    # github.io 실고객 사이트는 같은 주소 뿌리를 써서, 한 글의 스크립트가 다른 사이트 관리 열쇠를 노릴 수 있다.
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # 사진을 링크보다 먼저 처리한다. 링크 규칙이 ![alt](src)의 대괄호를 먼저
    # 물어가면 앞의 !만 글자로 남는다.
    def image(m):
        alt = (m.group(1) or "")[:80]
        src = safe_url(m.group(2))
        return f'<img src="{src}" alt="{alt}" loading="lazy">' if src else alt

    text = re.sub(r"!\[(.*?)\]\((.+?)\)", image, text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if re.match(r"https?://", url):
            return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'
        if not safe_url(url):
            return label
        # 주소가 아니면 같은 폴더의 다른 글로 본다.
        # 예전에는 여기서 빌드를 죽였는데, 자동 발행에서는 글 하나의 링크 오타가
        # 배포 전체를 멈춰 세운다. 죽은 링크를 내보내지 않으면 목적은 같으므로
        # 글자만 남기고 경고로 알린다.
        if url not in slugs:
            WARNINGS.append(f"링크 '{url}'에 해당하는 글이 없어 글자만 남겼습니다")
            return label
        return f'<a href="{url}.html">{label}</a>'

    return re.sub(r"\[(.+?)\]\((.+?)\)", link, text)


def md_to_html(md, slugs):
    html, para, ul, ol, quote, table = [], [], [], [], [], []

    def flush():
        if para:
            html.append("<p>" + inline(" ".join(para), slugs) + "</p>")
            para.clear()
        if ul:
            html.append("<ul>" + "".join(f"<li>{inline(i, slugs)}</li>" for i in ul) + "</ul>")
            ul.clear()
        if ol:
            # AI가 쓴 글은 "1. 첫째" 꼴 번호 목록을 자주 쓴다. 문단으로 흘리면
            # 번호가 글자로 남아 순서가 안 읽힌다.
            html.append("<ol>" + "".join(f"<li>{inline(i, slugs)}</li>" for i in ol) + "</ol>")
            ol.clear()
        if quote:
            html.append("<blockquote><p>" + inline(" ".join(quote), slugs) + "</p></blockquote>")
            quote.clear()
        if table:
            # 두 번째 줄이 |---|---| 구분선이면 그 줄만 버리고 첫 줄을 머리행으로 쓴다
            rows = [[c.strip() for c in r.strip("|").split("|")] for r in table]
            table.clear()
            sep = len(rows) > 1 and set("".join(rows[1])) <= set("-: ")
            body = rows[2:] if sep else rows[1:]
            head = "".join(f"<th>{inline(c, slugs)}</th>" for c in rows[0])
            trs = "".join(
                "<tr>" + "".join(f"<td>{inline(c, slugs)}</td>" for c in r) + "</tr>"
                for r in body
            )
            html.append('<div class="table-wrap"><table>'
                        f"<thead><tr>{head}</tr></thead><tbody>{trs}</tbody></table></div>")

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("|") and s.endswith("|"):
            if para or ul or ol or quote:
                flush()
            table.append(s)
        elif s.startswith("### "):
            flush(); html.append(f"<h3>{inline(s[4:], slugs)}</h3>")
        elif s.startswith("## "):
            flush(); html.append(f"<h2>{inline(s[3:], slugs)}</h2>")
        elif s == "---":
            flush(); html.append("<hr>")
        elif s.startswith("> "):
            if para or ul or ol:
                flush()
            quote.append(s[2:])
        elif s.startswith("- "):
            if para or ol or quote:
                flush()
            ul.append(s[2:])
        elif re.match(r"^\d{1,2}[.)]\s+\S", s):
            if para or ul or quote:
                flush()
            ol.append(re.sub(r"^\d{1,2}[.)]\s+", "", s))
        else:
            if ul or ol or quote:
                flush()
            para.append(s)
    flush()
    return "\n".join(html)


def load_lineup(cfg):
    """config의 lineup 값으로 메이커 폴더(engine/car/makers/<이름>/)를 정하고 차종 목록을 읽는다.

    메이커에 따라 달라지는 건 차종 목록·차종 그림뿐이고 코드·디자인은 전부 같다.
    신차가 나오면 그 메이커의 lineup.json 한 줄만 고치면 그 메이커 영업사원 전원에게 반영된다.
    """
    global MAKER
    name = (cfg.get("lineup") or "").strip()
    if not name:
        sys.exit("config.json에 lineup이 없습니다. 예: \"lineup\": \"kia\"")
    MAKER = ENGINE / "makers" / name
    path = MAKER / "lineup.json"
    if not path.exists():
        have = sorted(p.name for p in (ENGINE / "makers").iterdir() if (p / "lineup.json").exists())
        sys.exit(f"메이커 폴더가 없습니다: engine/car/makers/{name}/lineup.json\n"
                 f"  지금 있는 것: {', '.join(have) if have else '없음'}\n"
                 f"  새 메이커라면 makers/{name}/lineup.json 을 만들고 차종 그림(art/)을 넣으십시오.")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_post(path, slugs):
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
    meta["html"] = md_to_html(body, slugs)
    meta["text"] = body
    return meta


# ---------- 광고 표현 점검 ----------
def ad_check(posts, dealership=""):
    """보험의 '심의'에 해당하는 자리. 자동차는 사전 심의 기관이 없는 대신
    표시광고법(부당한 표시·광고)과 제조사 브랜드 사용 규정이 걸린다.
    걸리기 쉬운 표현만 걸러주는 보조 도구이고, 통과를 보장하지 않는다."""
    rules = [
        ("최상급·순위 표현 없음", r"최저가|최고가|업계 1위|전국 1위|판매 1위|최고 할인|가장 싸|국내 유일|최다"),
        ("할인액 단정 표현 없음", r"무조건 할인|확정 할인|반드시 할인|100% 할인|최대 할인 보장"),
        ("금리·할부 조건 단정 없음", r"무이자 할부|금리 0|이자 없|저금리 보장|승인 보장|누구나 승인"),
        ("출고 시기 단정 없음", r"즉시 출고|당일 출고|바로 출고|즉시 인도|출고 보장"),
        ("보조금 단정 표현 없음", r"보조금 확정|보조금 전액 보장|보조금 100%"),
        ("타사 비방 표현 없음", r"타사보다|경쟁사보다|다른 브랜드보다|타 브랜드 대비"),
    ]
    manual = [
        "제조사 상표·차량 이미지 사용이 대리점 브랜드 가이드 범위 안인가",
        "프로모션·가격을 적었다면 '○년 ○월 기준'과 조건이 함께 적혀 있는가",
        "할부·리스 조건에 '심사에 따라 달라진다'는 취지가 적혀 있는가",
        "실제 고객 사례·후기를 지어내 쓰지 않았는가",
    ]

    lines = [f"광고 표현 자동 점검 결과  ({date.today().isoformat()} 빌드)", "=" * 40, ""]
    ok = True
    for label, pattern in rules:
        hits = []
        for p in posts:
            for i, line in enumerate(p["text"].splitlines(), 1):
                if re.search(pattern, line):
                    hits.append(f"    {p['label']} {i}행: {line.strip()[:60]}")
        if hits:
            ok = False
            lines.append(f"[X] {label} — 위반 {len(hits)}건")
            lines.extend(hits)
        else:
            lines.append(f"[O] {label}")

    if dealership:
        lines += [
            "",
            f"[!] 소속 대리점명 표기 (의도적) — {dealership}",
            "    노출 위치: 히어로 뱃지, '이 사람은 누구인가' 소속란, 신원 확인 박스, 푸터",
            "    소속을 밝히는 것 자체는 문제가 아니라, 오히려 고객이 신원을 확인하게 해주는 장치입니다.",
            "    다만 제조사 상표(로고·워드마크)를 쓰는 방식은 대리점 브랜드 가이드의 통제를 받으므로,",
            "    로고 이미지를 넣을 계획이면 대리점을 통해 사용 가능 범위를 먼저 확인하십시오.",
            "    (표기 불가로 회신되면 config.json의 dealership을 비우고 재빌드 — 네 곳에서 함께 사라집니다)",
        ]

    lines += ["", "-- 자동 판정 불가, 발행 전 직접 확인 --"]
    lines += [f"[ ] {m}" for m in manual]
    lines += ["", "※ 본 점검은 법적 검토가 아니며, 표시광고법에서 문제되기 쉬운 표현을 걸러주는 보조 도구입니다."]
    return "\n".join(lines), ok


# ---------- 고객에게 요청할 준비물 (대표가 대신 못 하는 것만) ----------
def client_todo(cfg, root):
    """영업사원 본인만 줄 수 있는 항목을 추려 카톡에 붙여넣을 안내문을 만든다.

    한 번에 다 물어봐야 왕복이 한 번으로 끝난다. 1건당 소요 시간은 작업 시간이 아니라
    대기 시간 때문에 늘어난다.
    """
    hero = any((root / "assets" / f"hero{e}").exists() for e in (".webp", ".jpg", ".jpeg", ".png"))
    need = []
    if "xxxxxx" in cfg.get("kakao_url", ""):
        need.append((
            "카카오톡 오픈채팅 링크",
            "카톡 > 채팅 탭 > 오른쪽 위 [+] > 오픈채팅 > '1:1 채팅방' 선택\n"
            "     > 이름은 '차량 상담 문의' 정도로 > 완료 > 만들어진 방에서 링크 복사\n"
            "     ※ 본인 프로필 사진과 친구목록은 상대에게 보이지 않습니다\n"
            "     ※ 평소 쓰시는 카톡에서 그대로 알림 받고 답장하시면 됩니다",
        ))
    if "0000" in cfg.get("phone", ""):
        need.append(("본인 휴대폰 번호", "고객이 바로 거는 번호입니다"))
    if "0000" in cfg.get("dealership_phone", ""):
        need.append((
            "대리점 대표번호",
            "고객이 '이 사람이 여기 직원 맞나'를 직접 확인하는 용도로 홈페이지에 넣습니다\n"
            "     ※ 이 번호가 있고 없고가 첫 상담 성사율을 가릅니다",
        ))
    if "(" in cfg.get("employee_no", ""):
        need.append(("사원번호", "명함에 적힌 번호입니다. 대리점 대표번호와 함께 신원 확인용으로 씁니다"))
    # 실적 숫자는 페이지에서 가장 먼저 읽히는 정보다. 지어낸 숫자는 표시광고법 위반이므로
    # 값이 채워져 있든 아니든 매번 확인 항목으로 띄운다.
    stats = cfg.get("stats", [])
    if stats:
        labels = " / ".join(s["label"] for s in stats)
        need.append((
            "실적 숫자 " + str(len(stats)) + "개 확인  ★필수",
            labels + "\n"
            "     현재 값은 화면 확인용 샘플입니다. 실제 숫자를 알려주시면 그대로 바꿔 넣습니다.\n"
            "     ※ 정확한 집계가 어려우시면 '경력 O년', '후기 O건'처럼 셀 수 있는 것으로 바꿔도 됩니다.\n"
            "     ※ 확인되지 않은 숫자는 넣지 않습니다 (표시광고법)",
        ))
    if not str(cfg.get("years", "")).strip():
        need.append(("이 일 시작하신 연도", "예) 2018년 — 홈페이지에 '제천에서 O년'으로 들어갑니다"))
    if not cfg.get("youtube_url", "").strip():
        need.append((
            "유튜브 채널 주소 (있는 경우만)",
            "차량 소개나 상담 영상을 올리는 채널이 있으면 주소를 주세요\n"
            "     홈페이지에 '유튜브로 먼저 보기' 버튼이 생깁니다. 없으면 버튼 없이 나갑니다",
        ))
    if not hero:
        need.append((
            "본인 사진 1장",
            "세로로 찍은 사진. 전시장에서 차와 함께 찍은 것이면 가장 좋습니다\n"
            "     ※ 화면 맨 위를 꽉 채우는 사진이라 세로로 길게 찍어주셔야 합니다",
        ))
    shot = len(list((root / "assets" / "models").glob("*.jpg"))) if (root / "assets" / "models").exists() else 0
    if shot < 3:
        need.append((
            "전시장 차량 사진  ★필수",
            "전시차를 세로로 찍어서 보내주세요. 차종당 1장이면 됩니다\n"
            "     ※ 폰 세로 모드로, 차 전체가 들어오게 한 발 물러서서\n"
            "     ※ 제조사 카탈로그 사진은 상표 문제로 쓸 수 없습니다. 직접 찍으신 사진만 씁니다\n"
            "     ※ 직접 찍은 사진이 오히려 신뢰가 높습니다 (실제로 만지는 차니까요)\n"
            f"     현재 받은 사진: {shot}장",
        ))

    name = cfg.get("name", "고객")
    lines = [f"[{name} 님께 보낼 안내 — 카톡에 그대로 붙여넣으세요]", "",
             f"{name} 님, 홈페이지는 이미 만들어 두었습니다.",
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
        "   · 광고 표현 점검표 자동 작성",
        "",
        "■ 대리점에 미리 확인해 주실 것",
        "   · 개인 홈페이지 운영이 대리점 방침상 가능한지",
        "   · 제조사 로고를 페이지에 넣어도 되는지 (안 되면 글자 표기만 씁니다)",
        "",
    ]

    lines += ["-" * 46, "[대표님 확인용 — 고객 발송 시 이 아래는 지울 것]", "",
              f"  고객이 직접 해야 할 것: {len(need)}건",
              f"  도메인: {'미정 — site_url 수정 필요' if 'pages.dev' in cfg.get('site_url', '') else '설정됨'}",
              f"  문의 추적: {'꺼짐 — track_url 설정 필요' if not cfg.get('track_url') else '켜짐'}",
              f"  소속 대리점 표기: {cfg.get('dealership') or '(비표기)'} — 대리점 방침 확인 필요",
              "",
              "  [계정 취급 원칙]",
              "   절대 받지 말 것: 제조사 전산 계정, 금융·캐피탈 계정, 카톡 개인 비밀번호",
              "     → 사고 시 전적 책임. 자동 로그인은 구현 금지 항목.",
              "   권한 초대로 대체할 것: 카카오톡 채널, 구글 서치콘솔",
              "   비밀번호가 꼭 필요하면: 고객 PC에서 고객이 직접 로그인 (대행 보관 금지)"]
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
        "kakao_btn_sticky": btn("btn-kakao", "카톡 상담"),
        "kakao_btn_article": btn("btn-kakao", "카톡으로 물어보기"),
    }


# ---------- 검색 최적화 도우미 (homepage-seo 기준) ----------
def webp_img(rel, alt, sizes, attr):
    """원본 JPG/PNG → dist 에 WebP 400·800·1600 을 만들고 srcset·width·height 가 붙은 <img>.
    Pillow 가 없으면 원본 그대로(사진은 나오고 점검기 WARN 만 남는다)."""
    try:
        from PIL import Image
    except ImportError:
        return f'<img src="{quote(rel)}" alt="{alt}"{attr}>'
    with Image.open(src(rel)) as im:
        w, h = im.size
        stem = rel.rsplit(".", 1)[0]
        widths = sorted({x for x in (400, 800, 1600) if x < w} | {min(w, 1600)})
        for x in widths:
            out = DIST / f"{stem}-{x}.webp"
            out.parent.mkdir(parents=True, exist_ok=True)
            if not out.exists():
                im.convert("RGB").resize((x, round(h * x / w)), Image.LANCZOS).save(out, "WEBP", quality=80)
    # 화면을 꽉 채우는(cover) 사진은 화면 비율이 사진보다 좁으면 높이에 맞춰 늘어난다.
    # 그때 실제 폭 = 100vh × 사진 가로/세로. 이걸 안 알려주면 폰에서 작은 파일을 골라 흐려진다.
    if sizes == "cover":
        sizes = f"(max-aspect-ratio: {w}/{h}) {-(-100 * w // h)}vh, 100vw"
    # 차종 이름에 공백이 있어("카니발 하이리무진") srcset 이 깨지지 않게 주소를 인코딩한다
    srcset = ", ".join(f"{quote(f'{stem}-{x}.webp')} {x}w" for x in widths)
    return (f'<img src="{quote(f"{stem}-{widths[-1]}.webp")}" srcset="{srcset}" sizes="{sizes}" '
            f'width="{w}" height="{h}" alt="{alt}"{attr}>')


def channel_list(cfg):
    """config 의 channels(블로그·인스타·유튜브 등) + youtube_url + 준비된 카톡 채널. 빈 주소는 뺀다."""
    out = [c for c in cfg.get("channels", []) if (c.get("url") or "").strip()]
    yt = (cfg.get("youtube_url") or "").strip()
    if yt and all(c["url"] != yt for c in out):
        out.append({"name": "유튜브", "url": yt})
    kakao = (cfg.get("kakao_url") or "").strip()
    if kakao and "xxxxxx" not in kakao:
        out.append({"name": "카카오톡 채널", "url": kakao})
    return out


def same_as_urls(cfg):
    return [c["url"] for c in channel_list(cfg)]


def footer_channels(cfg):
    chs = channel_list(cfg)
    if not chs:
        return ""
    links = " · ".join(f'<a href="{escape(c["url"])}" target="_blank" rel="noopener me">{escape(c["name"])}</a>'
                       for c in chs)
    return f'<p class="legal foot-channels">채널: {links}</p>'


def llms_txt(cfg, site, posts, lineup, n_models):
    """AI 검색이 JS 없이 한 번에 읽는 요약본. 화면·JSON-LD 와 같은 값에서 나온다(NAP 통일)."""
    nl = "\n"
    models = ", ".join(m["name"] for g in lineup["groups"] for m in g["models"])
    return f"""# {cfg['region']} {cfg.get('brand', '')} 영업사원 {cfg['name']}

> {cfg['tagline']}

## 기본 정보
- 이름: {cfg['name']} ({cfg.get('brand', '')} 자동차 영업사원)
- 소속: {cfg.get('dealership') or '-'}
- 활동 지역: {cfg.get('region_official', cfg['region'])}
- 전화: {cfg['phone']}
- 홈페이지: {site}/
- 이 페이지는 영업사원 개인의 상담 안내 페이지이며 제조사·대리점 공식 홈페이지가 아닙니다.

## 하는 일
{nl.join(f"- {c}" for c in cfg.get('career', []))}

## 취급 차종 ({n_models}종)
{models}

## 자주 묻는 질문
{nl.join(f"- {f['q']} — {f['a']}" for f in cfg.get('faq', []))}

## 정리한 글
{nl.join(f"- [{p['title']}]({site}/posts/{p['slug']}.html) ({p.get('date', '')}): {p.get('description', '')}" for p in posts)}

## 채널
{nl.join(f"- {c['name']}: {c['url']}" for c in channel_list(cfg)) or '- (아직 없음)'}
"""


def page_404(cfg, phone_digits):
    """없는 주소용. 어느 깊이에서 열려도 깨지지 않게 CSS 는 안에 넣고 링크는 / 로 시작."""
    dark = cfg.get("theme", "premium-dark") != "bright"
    bg, fg, mute = ("#0a0b0d", "#f2efe8", "#9a968d") if dark else ("#ffffff", "#15171a", "#666")
    name = escape(cfg["name"])
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>페이지를 찾을 수 없습니다 | {escape(cfg['region'])} 영업사원 {name}</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:{bg};color:{fg};font-family:Pretendard,-apple-system,system-ui,sans-serif;word-break:keep-all;padding:24px;box-sizing:border-box}}
main{{max-width:440px;text-align:center}}
.n{{font-size:72px;font-weight:300;letter-spacing:.08em;margin:0;color:#c9a227}}
h1{{font-size:24px;margin:10px 0 12px;letter-spacing:-.02em}}
p{{line-height:1.7;color:{mute};margin:0 0 30px}}
a{{display:inline-block;margin:4px;padding:14px 24px;border:1px solid #c9a227;color:{fg};text-decoration:none;font-weight:600}}
a.s{{background:#c9a227;color:#0a0b0d}}
</style>
</head>
<body>
<main>
<p class="n">404</p>
<h1>찾으시는 페이지가 없습니다</h1>
<p>주소가 바뀌었거나 없어진 페이지입니다.<br>{name} 첫 화면에서 다시 찾아 주세요.</p>
<a class="s" href="/">첫 화면으로</a><a href="tel:{phone_digits}">전화 문의</a>
</main>
</body>
</html>
"""


def copy_indexnow_key():
    """IndexNow 키(32자리 hex.txt, 내용=파일명). 없으면 이 폴더에 하나 만들고 dist 로 복사.
    글해줌 발행기가 이 키로 새 글을 빙·네이버에 바로 알린다."""
    keys = [p for p in ROOT.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}\.txt", p.name)]
    if not keys:
        k = secrets.token_hex(16)
        (ROOT / f"{k}.txt").write_text(k, encoding="utf-8")
        keys = [ROOT / f"{k}.txt"]
    shutil.copy2(keys[0], DIST / keys[0].name)


# ---------- 렌더 ----------
def vcard(cfg, site):
    """'연락처 저장' 버튼이 내려주는 파일. 폰 주소록에 이름·소속·전화·홈페이지가 한 번에 들어간다."""
    def esc(s):
        return re.sub(r"([,;\\])", r"\\\1", s)
    org = cfg.get("dealership", "").strip()
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{esc(cfg['name'])}", f"N:{esc(cfg['name'])};;;;"]
    if org:
        lines.append(f"ORG:{esc(org)}")
    lines += [f"TITLE:{esc(cfg.get('brand', ''))} 영업사원", f"TEL;TYPE=CELL:{cfg['phone']}",
              f"URL:{site}/", f"NOTE:{esc(cfg['region'] + ' ' + cfg.get('brand', '') + ' 신차 상담')}",
              "END:VCARD", ""]
    return "\r\n".join(lines)


def offers_block(cfg):
    """이달 조건·재고 보유. until 이 지난 항목은 빌드에서 빠지고, 빌드 사이에 지나면 화면 스크립트가 숨긴다.
    조건·재고는 영업사원이 확인한 것만 넣는다(지어내면 표시광고법). 비면 섹션째 안 나온다."""
    today = date.today().isoformat()
    items = [o for o in cfg.get("offers", []) if not o.get("until") or o["until"] >= today]
    if not items:
        return ""
    rows = ""
    for o in items:
        until = o.get("until", "")
        model = o.get("model", "")
        rows += (
            f'<div class="offer reveal"' + (f' data-until="{until}"' if until else "") + '>'
            f'<p class="offer-kind">{escape(o.get("kind", "이달 조건"))}'
            + (' <span class="offer-sample">견본 예시</span>' if o.get("example") else "") + '</p>'
            f'<h3>{escape(o["title"])}</h3><p>{escape(o.get("detail", ""))}</p>'
            + (f'<p class="offer-until">{until}까지</p>' if until else "")
            + f'<a class="offer-ask" href="#contact"' + (f' data-model="{escape(model)}"' if model else "")
            + ' data-ev="offer">이 조건으로 문의</a></div>'
        )
    return ('<section class="sec" id="offers"><div class="wrap">'
            '<p class="eyebrow">This Month</p>'
            '<h2 class="sec-title reveal">이달 조건과 지금 재고가 있는 차</h2>'
            '<p class="sec-desc reveal">제가 직접 확인한 것만 올립니다. 조건은 기한이 지나면 이 화면에서 자동으로 내려갑니다.</p>'
            f'<div class="offers">{rows}</div></div></section>')


def deliveries_block(cfg, media):
    """출고 후기. 고객 동의를 받은 실제 인도 사진만. 평점·별점은 달지 않는다(자체 평점 schema 금지)."""
    items = [d for d in cfg.get("deliveries", []) if d.get("photo") and (ROOT / d["photo"]).exists()]
    if not items:
        return ""
    cards = "".join(
        f'<figure class="delivery reveal">'
        f'{media([d["photo"]], "출고 사진", sizes="(max-width: 700px) 50vw, 33vw", alt=d.get("model", "") + " 출고")}'
        f'<figcaption><strong>{escape(d.get("model", ""))}</strong> {escape(d.get("when", ""))}'
        + (f'<span>{escape(d["note"])}</span>' if d.get("note") else "") + '</figcaption></figure>'
        for d in items
    )
    return ('<section class="sec" id="deliveries"><div class="wrap">'
            '<p class="eyebrow">Deliveries</p>'
            '<h2 class="sec-title reveal">제가 출고해 드린 차들입니다</h2>'
            f'<div class="deliveries">{cards}</div></div></section>')


def ld(obj):
    """<script type="application/ld+json"> 안에 넣을 JSON. < > & 를 유니코드 이스케이프해 태그 탈출을 막는다."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def render(template, mapping):
    for k, v in mapping.items():
        template = template.replace("{{" + k + "}}", str(v))
    leftover = re.findall(r"{{\w+}}", template)
    if leftover:
        sys.exit(f"치환 안 된 자리표시자: {leftover}")
    return template


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    lineup = load_lineup(cfg)
    paths = sorted((ROOT / "content").glob("*.md"))
    slugs = {p.stem for p in paths}
    posts = sorted((parse_post(p, slugs) for p in paths),
                   key=lambda p: p.get("date", ""), reverse=True)

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "posts").mkdir(parents=True)
    # 공용 자산(엔진) → 메이커 원본 차 이미지 → 세대 자산(본인 사진 등) 순서로 겹쳐 싣는다
    shutil.copytree(ENGINE / "assets", DIST / "assets")
    if (MAKER / "cars").exists():
        shutil.copytree(MAKER / "cars", DIST / "assets" / "cars")
    if (ROOT / "assets").exists():
        shutil.copytree(ROOT / "assets", DIST / "assets", dirs_exist_ok=True)
    art_src = MAKER / "art" / cfg.get("theme", "premium-dark")
    if art_src.exists():
        shutil.copytree(art_src, DIST / "assets" / "art" / cfg.get("theme", "premium-dark"))

    def tpl(n):
        return (ENGINE / "templates" / n).read_text(encoding="utf-8")

    phone_digits = re.sub(r"\D", "", cfg["phone"])
    site = cfg["site_url"].rstrip("/")

    # 카톡 명함 카드는 파일명에 내용 해시를 붙인다.
    # 이름이 그대로면 카카오·페이스북이 예전 이미지를 계속 보여줘서, 사진을 바꿔도 반영되지 않는다.
    og_src = ROOT / "assets" / "og-card.jpg"
    if og_src.exists():
        # 카드에는 이름·실적이 그림으로 박혀 있는데 config.json에서 자동으로 다시 그려지지
        # 않는다. config를 고치고 카드를 안 다시 만들면 카톡 미리보기만 옛 이름으로 나간다.
        if og_src.stat().st_mtime < (ROOT / "config.json").stat().st_mtime:
            WARNINGS.append(
                "카톡 명함 카드(assets/og-card.jpg)가 config.json보다 오래됐습니다 — "
                "이름·실적을 고치셨다면 make_art.py를 다시 돌리십시오"
            )
        og_name = f"og-card-{hashlib.md5(og_src.read_bytes()).hexdigest()[:8]}.jpg"
        shutil.copy2(og_src, DIST / "assets" / og_name)
        og_meta = (f'<meta property="og:image" content="{site}/assets/{og_name}">'
                   '<meta property="og:image:width" content="1200">'
                   '<meta property="og:image:height" content="630">'
                   '<meta name="twitter:card" content="summary_large_image">')
    else:
        # 카드가 없으면 og:image를 아예 내보내지 않는다. 404 이미지를 물리는 것보다 낫다.
        og_meta = ""

    theme = cfg.get("theme", "premium-dark")

    # 사진 우선순위: 실사진 → 생성 배경 아트 → 빈 자리표시자.
    # 실사진이 assets/models/에 들어오는 순간 그쪽으로 자동으로 갈아끼워진다.
    def media(candidates, label, eager=False, sizes="100vw", alt=""):
        for rel in candidates:
            if rel and src(rel).exists():
                attr = ' fetchpriority="high" decoding="async"' if eager else ' loading="lazy" decoding="async"'
                return webp_img(rel, alt, sizes, attr)
        return f'<div class="ph" data-ph="{label}"></div>'

    def art(name):
        return "assets/art/%s/%s.jpg" % (theme, name)

    dealership = cfg.get("dealership", "").strip()
    common = {
        "name": cfg["name"],
        "theme": theme,
        # 모바일 브라우저 주소창까지 페이지 색으로 물들인다 (명함으로 열었을 때 첫인상)
        "theme_color": "#ffffff" if theme == "bright" else "#0a0b0d",
        "brand": cfg.get("brand", ""),
        "dealership": dealership,
        "dealership_phone": cfg.get("dealership_phone", ""),
        "employee_no": cfg.get("employee_no", ""),
        "region": cfg["region"],
        "region_official": cfg.get("region_official", cfg["region"]),
        "eyebrow": cfg.get("eyebrow") or f"{cfg['region']} 자동차 영업사원",
        "years": cfg["years"],
        "tagline": cfg["tagline"],
        "phone": cfg["phone"],
        "phone_link": f"tel:{phone_digits}",
        "kakao_url": cfg["kakao_url"],
        # 카톡 주소가 아직 자리표시자면 버튼을 아예 내보내지 않는다. 죽은 링크보다 없는 편이 낫다.
        **_kakao_buttons(cfg.get("kakao_url", "")),
        # 유튜브는 '먼저 만나보는' 통로다. 주소가 없으면 버튼을 안 내보낸다.
        "youtube_btn": (
            f'<a class="btn btn-line" href="{cfg["youtube_url"]}" target="_blank" '
            f'rel="noopener" data-ev="youtube">유튜브로 먼저 보기</a>'
            if cfg.get("youtube_url", "").strip() else ""
        ),
        "site_url": site,
        # 통계·문의함에서 이 사이트를 가리키는 이름. github.io 는 여러 고객이 같은 호스트라 경로까지 붙인다
        "site_id": re.sub(r"^https?://", "", site),
        "og_meta": og_meta,
        "track_url": cfg["track_url"],
        "hero_image": cfg.get("hero_image", "assets/hero.svg"),
        "year": date.today().year,
        # GEO 최신성: 빌드할 때마다 오늘 날짜가 바닥글에 찍힌다 (글해줌 발행 = 빌드)
        "updated": f'<time datetime="{date.today().isoformat()}">{date.today().isoformat()}</time>',
        "footer_channels": footer_channels(cfg),
        # 통계를 켰을 때만 고지한다(개인정보 처리 투명성). 개인 링크 열람 알림까지 숨김 없이 적는다.
        "privacy_note": ('<p class="legal">이 페이지는 방문 수·유입 경로·버튼 누른 횟수를 개인을 알아볼 수 없는 숫자로만 집계합니다. '
                         '담당자가 보내 드린 개인 안내 링크로 여시면 열어 보신 사실이 담당자에게 전달됩니다.</p>'
                         if cfg.get("track_url") else ""),
        "naver_verification_meta": (
            f'<meta name="naver-site-verification" content="{cfg["naver_verification"]}">'
            if cfg.get("naver_verification") else ""
        ),
        "robots_meta": (
            '<meta name="robots" content="noindex, nofollow">'
            if any(h in site for h in ("pages.dev", "netlify.app", "vercel.app", "github.io", "example.com"))
            else ""
        ),
    }

    # 섹션 조립
    career_items = "".join(f"<li>{c}</li>" for c in cfg["career"])
    if dealership:
        career_items += f"<li>소속: {dealership}</li>"

    # 실적 숫자. 조사한 세일즈 왕 사이트들이 전부 설명보다 숫자를 먼저 보여준다.
    stat_items = "".join(
        f'<div class="stat reveal"><p class="stat-value">{s["value"]}'
        f'<span class="unit">{s.get("unit", "")}</span></p>'
        f'<p class="stat-label">{s["label"]}</p></div>'
        for s in cfg.get("stats", [])
    )

    def situation_card(s):
        body = f'<h3>{s["title"]}</h3><p>{s["desc"]}</p>'
        link = s.get("link")
        if not link:
            return f'<div class="card reveal">{body}</div>'
        if link not in slugs:
            sys.exit(f"상황 카드 '{s['title']}'의 link '{link}'에 해당하는 글이 content/에 없습니다. "
                     f"사용 가능: {sorted(slugs)}")
        label = s.get("link_label", "자세히 보기")
        return (f'<a class="card reveal" href="posts/{link}.html">{body}'
                f'<span class="card-more">{label}</span></a>')

    situation_cards = "".join(situation_card(s) for s in cfg["situations"])

    # 대표 차종 한 대를 화면 전체로. 제조사가 절대 쓸 수 없는 문장을 얹는 자리다.
    # 영상은 유튜브 '임베드'만 쓴다 — 남의 영상에서 화면을 캡처해 올리면 저작권 문제.
    # 탭하기 전엔 iframe 을 넣지 않아 첫 화면이 무거워지지 않는다 (index.html 스크립트가 끼움).
    def feature_video_btn(feat):
        m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/)([\w-]{11})", feat.get("video", ""))
        if not m:
            return ""
        label = feat.get("video_label") or f"{feat['name']} 영상으로 보기"
        return (f'<button type="button" class="btn btn-line feature-play" data-yt="{m.group(1)}" '
                f'data-ev="feature-video">{label}</button>')

    feat = lineup.get("featured")
    if feat:
        feat_media = media(["assets/models/%s.jpg" % feat["name"], art("feature")],
                           feat["name"] + " 사진 자리", sizes="cover")
        feature_block = (
            '<section class="feature">'
            f'<div class="feature-media">{feat_media}</div>'
            '<div class="feature-inner wrap">'
            f'<p class="eyebrow">{cfg.get("brand", "")} {feat["name"]}</p>'
            f'<h2 class="feature-name">{feat["name"]}</h2>'
            f'<p class="feature-copy">{feat["copy"]}</p>'
            f'<p class="feature-note">{feat.get("note", "")}</p>'
            '<div class="hero-cta">'
            f'<a class="btn btn-line" href="#contact" data-model="{feat["name"]}">'
            f'{feat["name"]} 문의하기</a>'
            + feature_video_btn(feat)
            + '</div>'
            '</div></section>'
        )
    else:
        feature_block = ""

    # 신원 확인 박스. 보험은 협회 조회가 있지만 자동차는 없어서, 소속 대리점 대표번호가
    # 유일한 확인 수단이다. 둘 다 비어 있으면 박스 자체를 내보내지 않는다 —
    # 확인할 방법이 없는 '확인해 보세요' 박스는 오히려 신뢰를 깎는다.
    dealer_tel = re.sub(r"\D", "", cfg.get("dealership_phone", ""))
    emp_no = cfg.get("employee_no", "").strip()
    if dealership and dealer_tel and "0000" not in cfg.get("dealership_phone", ""):
        verify_box = (
            '<div class="verify reveal" id="verify">'
            '<p class="eyebrow">Verify</p>'
            '<p class="verify-desc" style="margin-top:14px">처음 연락하는 사람에게 차 이야기를 꺼내는 것이 '
            f'조심스러운 건 당연합니다. {dealership} 대표번호로 전화해 제 이름을 대시면 재직 여부를 '
            '바로 확인하실 수 있습니다. 확인하신 뒤에 연락 주셔도 됩니다.</p>'
            + (f'<p class="verify-no">사원번호 {emp_no}</p>'
               if emp_no and "(" not in emp_no else "")
            + f'<a class="verify-link" href="tel:{dealer_tel}" data-ev="tel-dealer">'
            f'{dealership} {cfg["dealership_phone"]}</a></div>'
        )
    else:
        verify_box = ""

    # 차종은 제조사 사이트로 내보내지 않고, 그 차종이 적힌 견적 문의로 보낸다.
    # 애써 들어온 사람을 제조사 페이지로 흘려보내면 문의가 거기서 끝난다.
    model_groups = ""
    n_models = 0
    for g in lineup["groups"]:
        items = ""
        for m in g["models"]:
            name = m["name"]
            copy = m.get("copy", "")
            cat = (m.get("catalog") or "").strip()
            # 카탈로그는 기아 서버 주소로 '연결'만 한다. 내려받아 재배포하면 저작권 문제가 된다.
            # 주소가 비어 있으면 버튼을 아예 안 내보낸다 (죽은 링크보다 없는 편이 낫다).
            # KGM처럼 차종별 PDF 주소가 없는 메이커는 목록 페이지로 보내므로 문구가 달라진다.
            cat_label = lineup.get("catalog_label") or "카탈로그"
            cat_btn = (f'<a class="model-cat" href="{cat}" target="_blank" rel="noopener nofollow" '
                       f'data-ev="catalog" aria-label="{name} {cat_label} (새 창)">{cat_label}</a>') if cat else ""
            items += (
                f'<div class="model" data-model="{name}">'
                f'<a class="model-hit" href="#contact" data-model="{name}">'
                f'{media(["assets/models/%s.jpg" % name, art(name)], "사진 자리", sizes="(max-width: 700px) 50vw, 25vw")}'
                f'<span class="model-info"><span class="model-name">{name}</span>'
                + (f'<span class="model-copy">{copy}</span>' if copy else "")
                + f'</span></a>{cat_btn}</div>'
            )
        n_models += len(g["models"])
        model_groups += (f'<div class="model-group reveal" data-group>'
                         f'<h3>{g["name"]} · {len(g["models"])}종</h3>'
                         f'<div class="model-grid">{items}</div></div>')

    posts_list = "".join(
        f'<a class="post-row reveal" href="posts/{p["slug"]}.html">'
        f'<span class="post-no">{i:02d}</span>'
        f'<span class="post-title">{escape(p["title"])}</span>'
        f'<span class="post-desc">{escape(p.get("description", ""))}</span></a>'
        for i, p in enumerate(posts, 1)
    )

    # 소속 뱃지는 dealership이 채워져 있을 때만 붙인다. 따로 하드코딩하면
    # 대리점이 표기 불가로 회신했을 때 config만 비워도 뱃지에 이름이 남아 롤백이 새어나간다.
    chip_list = list(cfg.get("chips", []))
    if dealership:
        chip_list.insert(0, dealership)
    chips = "".join(f"<span class='chip'>{c}</span>" for c in chip_list)

    principle_items = "".join(
        f'<div class="principle reveal"><h3>{p["title"]}</h3><p>{p["desc"]}</p></div>'
        for p in cfg.get("principles", [])
    )
    process_steps = "".join(
        f'<div class="step reveal"><span class="step-no">STEP {i:02d}</span>'
        f'<h3>{s["title"]}</h3><p>{s["desc"]}</p></div>'
        for i, s in enumerate(cfg.get("process", []), 1)
    )
    faq_items = "".join(
        f'<details class="faq reveal"><summary>{f["q"]}</summary><p>{f["a"]}</p></details>'
        for f in cfg.get("faq", [])
    )

    # 판매사원 개인 페이지이므로 Person, 소속은 worksFor로 건다 (대리점 자체를 사칭하지 않게)
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": cfg["name"],
        "jobTitle": "자동차 영업사원",
        "description": cfg["tagline"],
        "telephone": cfg["phone"],
        "url": site,
        "areaServed": [cfg["region"], cfg.get("region_official", cfg["region"])],
    }
    if dealership:
        person["worksFor"] = {"@type": "AutoDealer", "name": dealership}
    if og_meta:
        person["image"] = f"{site}/assets/{og_name}"
    # sameAs: 같은 사람의 다른 주소(블로그·인스타·유튜브·카톡 채널). AI가 '이 사람이 그 사람'이라고 묶는 끈.
    same_as = same_as_urls(cfg)
    if same_as:
        person["sameAs"] = same_as
    jsonld = ld(person)
    faq_jsonld = ld({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in cfg.get("faq", [])
        ],
    })

    index = render(tpl("index.html"), {
        **common,
        "hero_media": media([cfg.get("hero_image", ""), art("hero")], "인물 사진 자리", eager=True, sizes="cover",
                            alt=f"{cfg['region']} {cfg.get('brand', '')} 영업사원 {cfg['name']}"),
        "hero_claim": cfg.get("hero_claim", ""),
        "intro_lead": cfg.get("intro_lead", ""),
        "intro": cfg["intro"],
        "stat_items": stat_items,
        "career_items": career_items,
        "situation_cards": situation_cards,
        "verify_box": verify_box,
        "feature_block": feature_block,
        "model_groups": model_groups,
        "model_count": f"{n_models}종 취급",
        "model_options": "".join(f'<option value="{escape(m["name"])}">'
                                 for g in lineup["groups"] for m in g["models"]),
        "offers_block": offers_block(cfg),
        "deliveries_block": deliveries_block(cfg, media),
        # 할부를 금융사에 연결(모집)하는 분은 등록번호 고지가 필요할 수 있다. 값이 있을 때만 출력.
        "finance_notice": (f'<p class="legal">{escape(cfg["finance_notice"])}</p>'
                           if cfg.get("finance_notice", "").strip() else ""),
        "posts_list": posts_list,
        "chips": chips,
        "principle_items": principle_items,
        "process_steps": process_steps,
        "faq_items": faq_items,
        "jsonld": jsonld,
        "faq_jsonld": faq_jsonld,
    })
    (DIST / "index.html").write_text(index, encoding="utf-8")

    for p in posts:
        url = f"{site}/posts/{p['slug']}.html"
        author = {"@type": "Person", "name": cfg["name"], "url": f"{site}/", "jobTitle": "자동차 영업사원"}
        article = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": p["title"], "description": p.get("description", ""),
            "datePublished": p.get("date", ""), "dateModified": p.get("updated") or p.get("date", ""),
            "author": author, "publisher": author, "inLanguage": "ko",
            "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url,
        }
        if og_meta:
            article["image"] = f"{site}/assets/{og_name}"
        crumbs = {
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": f"{cfg['region']} {cfg.get('brand', '')} 영업사원 {cfg['name']}", "item": f"{site}/"},
                {"@type": "ListItem", "position": 2, "name": p["title"], "item": url},
            ],
        }
        page = render(tpl("post.html"), {
            **common,
            "title": escape(p["title"]),
            "description": escape(p.get("description", "")),
            "date": p.get("date", ""),
            "slug": p["slug"],
            "content": p["html"],
            "article_jsonld": ld(article),
            "crumbs_jsonld": ld(crumbs),
        })
        (DIST / "posts" / f"{p['slug']}.html").write_text(page, encoding="utf-8")

    # SEO: sitemap + robots (발행 시마다 자동 갱신)
    urls = [(f"{site}/", date.today().isoformat())] + [
        (f"{site}/posts/{p['slug']}.html", p.get("updated") or p.get("date", "")) for p in posts]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"  <url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>\n"
                         for u, d in urls) + "</urlset>\n")
    (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    # 임시 배포 주소는 색인을 막는다. 버릴 주소에 검색을 쌓으면 도메인 이전 때 그만큼 손해.
    staging = any(h in site for h in ("pages.dev", "netlify.app", "vercel.app", "github.io", "example.com"))
    if staging:
        (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    else:
        (DIST / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nDisallow: /admin.html\nSitemap: {site}/sitemap.xml\n"
            + (f"#DaumWebMasterTool:{cfg['daum_verification']}\n" if cfg.get("daum_verification") else ""),  # 다음 웹마스터도구 소유 확인
            encoding="utf-8")

    (DIST / "llms.txt").write_text(llms_txt(cfg, site, posts, lineup, n_models), encoding="utf-8")
    (DIST / "404.html").write_text(page_404(cfg, phone_digits), encoding="utf-8")
    copy_indexnow_key()
    # 사장님 관리 화면. admin_repo 가 비어 있으면(판매 전 견본) 저장 안 되는 '견본 모드'로 열린다.
    repo = cfg.get("admin_repo", "").strip()
    (DIST / "admin.html").write_text(render(tpl("admin.html"), {
        "name": escape(cfg["name"]), "site": site, "track": cfg.get("track_url", "").rstrip("/"),
        "repo": repo, "branch": cfg.get("admin_branch", "main"),
        "key": "car_admin_" + re.sub(r"\W", "_", repo or site),
    }), encoding="utf-8")
    if repo and (ROOT / "admin-key.json").exists():  # 토큰을 비밀번호로 잠근 파일
        shutil.copy2(ROOT / "admin-key.json", DIST / "admin-key.json")
    if not repo:
        demo_keys = ("name", "brand", "region", "dealership", "phone", "tagline", "hero_claim", "kakao_url",
                     "youtube_url", "channels", "offers", "deliveries", "finance_notice", "hero_image")
        (DIST / "admin-demo.json").write_text(
            json.dumps({k: cfg.get(k) for k in demo_keys}, ensure_ascii=False), encoding="utf-8")

    # 연락처 저장 파일 + 명함·전시장 인쇄용 QR (SVG는 화면용, PNG는 인쇄소용)
    (DIST / "contact.vcf").write_bytes(vcard(cfg, site).encode("utf-8"))
    qr = segno.make(f"{site}/?from=qr", error="m")  # from=qr: 통계에서 명함·전시장 QR로 온 방문을 따로 센다
    qr.save(DIST / "qr.svg", scale=6, border=2)
    qr.save(DIST / "qr.png", scale=24, border=2)

    # config.json도 화면에 그대로 노출되므로 글과 같은 기준으로 검사한다.
    # dealership은 의도적 표기라 일반 스캔에서 빼고 [!] 항목으로 따로 고지한다.
    scanned = {k: v for k, v in cfg.items() if k not in ("dealership", "dealership_phone_note")}
    cfg_doc = {"label": "config.json", "text": json.dumps(scanned, ensure_ascii=False, indent=1)}
    checklist, ok = ad_check(posts + [cfg_doc], dealership)
    # dist/에 두면 사이트와 함께 공개된다(누구나 /광고점검표.txt 로 열람, 11/17 발견). 작업 폴더에만 둔다.
    (ROOT / "광고점검표.txt").write_text(checklist, encoding="utf-8")
    print(checklist)
    print()

    # 고객에게 요청할 준비물 안내 (배포물이 아니므로 dist/가 아닌 작업 폴더에 둔다)
    todo, todo_n = client_todo(cfg, ROOT)
    (ROOT / "고객에게_보낼_안내.txt").write_text(todo, encoding="utf-8")

    # 보안 머리글 A+ (11/17, 두 단지 공용 engine/sec_headers.py). dist 를 다 지은 뒤 마지막에 — 페이지 안 코드 지문을 떠야 하므로.
    # 바깥: 글꼴(구글·jsdelivr), 시승 영상(youtube-nocookie), 문의·열람 서버(track_url). 관리 화면은 GitHub API·문의 서버만.
    sys.path.insert(0, str(ENGINE.parent))
    import sec_headers
    track = re.match(r"https?://[^/]+", cfg.get("track_url") or "")
    n_js, n_on = sec_headers.write(
        DIST, style="https://fonts.googleapis.com https://cdn.jsdelivr.net", font="https://fonts.gstatic.com https://cdn.jsdelivr.net",
        frame="https://www.youtube-nocookie.com", connect=track.group(0) if track else "",
        admin=("admin.html",), admin_connect=track.group(0) if track else "")
    print(f"보안 머리글: dist/_headers (페이지 안 스크립트 {n_js}개·인라인 이벤트 {n_on}개 지문 허용, 관리 화면 따로)")

    if not cfg["track_url"]:
        print("[경고] track_url이 비어 있어 문의 추적이 꺼진 상태로 빌드됨 (추적이 없으면 성과를 못 보여줌)")
    if todo_n:
        print(f"[대기] 고객에게 받을 것 {todo_n}건 → 고객에게_보낼_안내.txt (카톡 붙여넣기용)")
    for w in WARNINGS:
        print(f"[경고] {w}")
    print(f"빌드 완료: dist/  (글 {len(posts)}편, 차종 {n_models}종, "
          f"광고표현 자동점검 {'통과' if ok else '위반 있음 — 위 목록 확인'})")
    # 자동 발행(publish.py)이 이 결과를 보고 배포 여부를 정한다.
    # 광고 표현 위반이 있는 글은 사람이 볼 때까지 올리지 않는다.
    return {"ok": ok, "posts": len(posts), "warnings": list(WARNINGS)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("사용법: python build.py <세대 폴더>  예) python build.py ../../units/demo-kgm")
    use_unit(sys.argv[1])
    main()
