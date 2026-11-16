# -*- coding: utf-8 -*-
"""숙박 평면도 — 세대 폴더(site.config.json + images/) → 세대/dist/

    python -X utf8 build.py <세대 폴더>

화면 틀·디자인·SEO 뼈대는 여기(engine/stay) 하나뿐이고, 값은 세대의 site.config.json 에만 있다.
디자인은 더뷰(the-view) 견본에서 가져왔다(리조트급: 꽉 찬 사진·명조·채도 낮은 포인트색).
빈 값은 그 칸이 화면에서 통째로 빠진다 — 손님 화면에 [확인 필요] 같은 자리표시를 내보내지 않는다.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

from PIL import Image

ENGINE = Path(__file__).resolve().parent
T, S = ENGINE / "templates", ENGINE / "static"
ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICO = {
    "call": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
    "pin": '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "cal": '<rect x="3" y="4" width="18" height="18"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "menu": '<path d="M3 7h18M3 12h18M3 17h18"/>', "x": '<path d="M6 6l12 12M18 6L6 18"/>',
}
ico = lambda k: ICON.format(ICO[k])
MENU = [("rooms.html", "객실"), ("guide.html", "이용 안내"), ("around.html", "오시는 길"), ("blog.html", "소식")]


def fill(tpl, v):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(v[m.group(1)]), tpl)


def ld(*objs):
    return "\n".join('<script type="application/ld+json">' + json.dumps(o, ensure_ascii=False).replace("<", "\\u003c") + "</script>" for o in objs if o)


def faq_ld(items):
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]} if items else None


def lines(text):
    return "<br>".join(escape(x) for x in str(text).splitlines() if x.strip())


def main(U):
    cfg = json.loads((U / "site.config.json").read_text(encoding="utf-8"))
    D = U / "dist"
    today = datetime.date.today()
    name, phone, a, g = cfg["name"], cfg.get("phone", ""), cfg["address"], cfg.get("geo") or {}
    tel = re.sub(r"\D", "", phone)
    domain = cfg.get("domain", "").rstrip("/")
    base = os.environ.get("BASE", "").rstrip("/") or domain or cfg["preview_url"].rstrip("/")
    noindex = cfg.get("photos_temporary", True) or not domain
    addr = a["road"]
    book = cfg.get("booking_url", "")
    rooms = [r for r in cfg.get("rooms", []) if r.get("name")]
    faq, points, guide = cfg.get("faq", []), cfg.get("points", []), cfg.get("guide", [])
    alts = cfg.get("photo_alts", {})
    rv = cfg.get("reviews") or {}

    shutil.rmtree(D, ignore_errors=True)
    (D / "images").mkdir(parents=True)
    size = {}

    def prep(stem):
        if stem not in size:
            src = Image.open(U / "images" / f"{stem}.jpg").convert("RGB")
            for w, suf in ((1600, ""), (800, "-800"), (400, "-400")):
                im = src.copy()
                im.thumbnail((w, w * 2))
                im.save(D / "images" / f"{stem}{suf}.webp", quality=80, method=6)
            size[stem] = src.size
        return size[stem]

    def img(stem, alt, sizes="(min-width: 1024px) 50vw, 100vw", eager=False):
        w, h = prep(stem)
        load = 'fetchpriority="high"' if eager else 'loading="lazy"'
        return (f'<img src="{base}/images/{stem}-800.webp" srcset="{base}/images/{stem}-400.webp 400w, {base}/images/{stem}-800.webp 800w, '
                f'{base}/images/{stem}.webp 1600w" sizes="{sizes}" width="{w}" height="{h}" alt="{escape(alt)}" {load} decoding="async">')

    alt_of = lambda stem, fallback: alts.get(stem) or f"{name} {fallback}"

    # 공유 카드 1200x630
    hero = cfg["hero"]
    og = Image.open(U / "images" / f"{hero}.jpg").convert("RGB")
    W, H = og.size
    h = min(H, int(W * 630 / 1200))
    og.crop((0, (H - h) // 2, W, (H - h) // 2 + h)).resize((1200, 630)).save(D / "og.jpg", quality=85)
    og_image = f"{base}/og.jpg"

    route_url = (f"https://map.kakao.com/link/to/{quote(name)},{g['lat']},{g['lng']}" if g.get("lat")
                 else f"https://map.kakao.com/link/search/{quote(addr)}")
    naver_map = cfg.get("place_url") or f"https://map.naver.com/p/search/{quote(addr)}"
    same_as = [u for u in (cfg.get("place_url"),) + tuple(cfg.get("channels", [])) if u]
    css_v = hashlib.md5((S / "site.css").read_bytes()).hexdigest()[:8]
    js_v = hashlib.md5((S / "site.js").read_bytes()).hexdigest()[:8]
    mark = (S / "favicon.svg").read_text(encoding="utf-8").strip().replace("<svg ", '<svg aria-hidden="true" ', 1)
    shell = (T / "shell.html").read_text(encoding="utf-8")

    # 연락: 전화가 있으면 전화, 네이버 예약이 있으면 예약 — 메뉴·바닥·폰 하단 바·예약 칸이 같은 값을 쓴다
    links = ([(f"tel:{tel}", f"전화 {phone}", "call", False)] if tel else []) + ([(book, "네이버 예약", "cal", True)] if book else [])
    ext = lambda new: ' target="_blank" rel="noopener"' if new else ""
    sheet_call = "".join(f'<a class="call" href="{escape(u)}"{ext(n)}>{escape(t)}</a>' for u, t, _, n in links[:1])
    foot_contact = " · ".join(f'<a href="{escape(u)}"{ext(n)}>{escape(phone if k == "call" else t)}</a>' for u, t, k, n in links) or ""
    bar = "".join(f'<a href="{escape(u)}"{ext(n)}>{ico(k)}{"전화" if k == "call" else "예약"}</a>' for u, t, k, n in links[:2])
    book_html = ('<div class="ask ask-links">' + "".join(
        f'<a class="btn {"btn-fill" if i == 0 else "btn-line"}" href="{escape(u)}"{ext(n)}>{ico(k)}{"네이버 예약에서 빈 날짜 보기" if k == "cal" else escape(t)}</a>'
        for i, (u, t, k, n) in enumerate(sorted(links, key=lambda x: x[2] != "cal"))) + "</div>") if links else ""

    def page(path, title, desc, body, lds, og_title=None, extra="", preload="", current=None):
        menu = "".join(f'<a href="{base}/{p}"{" aria-current=" + chr(34) + "page" + chr(34) if p == current else ""}>{t}</a>' for p, t in [("index.html", "처음")] + MENU)
        out = D / path
        out.write_text(fill(shell, dict(
            robots='<meta name="robots" content="noindex">' if noindex or path == "404.html" else "",
            title=escape(title), description=escape(desc), url=f"{base}/{path}" if path != "index.html" else f"{base}/",
            name=escape(name), og_title=escape(og_title or title), og_image=og_image, base=base, verify="",
            css_v=css_v, js_v=js_v, preload=preload, ld=ld(*lds), ga4="", mark=mark, menu=menu,
            ico_menu=ico("menu"), ico_x=ico("x"), ico_pin=ico("pin"), snd="", body=body, addr=escape(addr),
            checkin=escape(cfg.get("checkin") or "문의"), checkout=escape(cfg.get("checkout") or "문의"),
            sheet_call=sheet_call, foot_contact=foot_contact, bar=bar,
            foot_menu="".join(f'<li><a href="{base}/{p}">{t}</a></li>' for p, t in MENU),
            channels="".join(f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{"네이버 플레이스" if "naver.com" in u else escape(u)}</a></li>' for u in same_as) or "<li>준비 중</li>",
            biz="", year=today.year, updated=today.isoformat(), route_url=route_url, extra=extra)), encoding="utf-8")

    def crumbs(path, title):
        return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": f"{base}/"},
            {"@type": "ListItem", "position": 2, "name": title, "item": f"{base}/{path}"}]}

    faq_html = lambda items: "".join(f'<details><summary>{escape(q)}</summary><p>{escape(x)}</p></details>' for q, x in items)
    sec = lambda inner, cls="": f'<section{" class=" + chr(34) + cls + chr(34) if cls else ""}><div class="wrap">{inner}</div></section>'
    head = lambda h2, lead="": f'<div class="head rv"><h2>{escape(h2)}</h2>{"<p class=" + chr(34) + "lead" + chr(34) + ">" + escape(lead) + "</p>" if lead else ""}</div>'
    times = " ".join(x for x in (f"입실 {cfg['checkin']}" if cfg.get("checkin") else "", f"퇴실 {cfg['checkout']}" if cfg.get("checkout") else "") if x)

    # ── 첫 화면 ───────────────────────────────────────────────────────────
    hw, hh = prep(hero)
    hero_pic = (f'<picture><img src="{base}/images/{hero}-800.webp" srcset="{base}/images/{hero}-800.webp 800w, {base}/images/{hero}.webp 1600w" sizes="100vw" '
                f'width="{hw}" height="{hh}" alt="{escape(cfg.get("hero_alt") or alt_of(hero, "전경"))}" fetchpriority="high" decoding="async"></picture>')
    preload = f'<link rel="preload" as="image" href="{base}/images/{hero}-800.webp" imagesrcset="{base}/images/{hero}-800.webp 800w, {base}/images/{hero}.webp 1600w" imagesizes="100vw">'
    tagline = "".join(f"<span><i>{escape(x.strip())}</i></span>" for x in (cfg.get("tagline") or name).split("|"))
    body = (f'<section class="hero">{hero_pic}<div class="wrap"><span class="label up" style="--d:.5s">{escape(cfg.get("hero_label", ""))}</span>'
            f'<h1>{tagline}</h1>' + (f'<p class="up" style="--d:1.25s">{escape(cfg["hero_sub"])}</p>' if cfg.get("hero_sub") else "")
            + f'<div class="cta on-dark up" style="--d:1.5s"><a class="btn btn-line" href="#book">예약 문의</a></div></div></section>')

    # 손님 후기 — 실제 출처(네이버 방문자 리뷰)·기준일과 함께 숫자만. 자체 평점·Review schema 없음
    voted = [(k.strip(), n) for k, n in rv.get("voted", [])[:4] if n]
    praise = (f'<p class="rating rv"><b>{rv["visitor_total"]}</b> <a href="{escape(naver_map)}" target="_blank" rel="noopener">네이버 방문자 리뷰</a>'
              f'<small>{rv.get("as_of", "")} 기준 · 손님이 가장 많이 고른 말 · '
              + " · ".join(f'<span style="white-space:nowrap">{escape(k)} {n}명</span>' for k, n in voted) + '</small></p>') if rv.get("visitor_total") and voted else ""
    if cfg.get("statement"):
        body += (f'<section class="declare"><div class="wrap"><h2 class="rv">{escape(cfg["statement"])}</h2>'
                 + (f'<p class="rv">{escape(cfg["declare_sub"])}</p>' if cfg.get("declare_sub") else "") + praise + "</div></section>")

    used = {hero}
    if len(points) >= 3:  # 세 장면: [작은 말, 제목, 설명, 사진]
        figs = ""
        for i, (word, title, text, stem) in enumerate(points[:3]):
            used.add(stem)
            fig = (f'<figure class="rv{" big" if i == 0 else ""}">{img(stem, alt_of(stem, title), "(min-width: 1024px) 58vw, 100vw" if i == 0 else "(min-width: 1024px) 40vw, 100vw")}'
                   f'<figcaption><span class="word">{escape(word)}</span><h3>{escape(title)}</h3><p>{escape(text)}</p></figcaption></figure>')
            figs += fig + ('<div class="side">' if i == 0 else "")
        body += sec(f'<div class="three">{figs}</div></div>')

    room_card = lambda r: (f'<figure class="rv">{img(r["photo"], alt_of(r["photo"], r["name"] + " 객실"), "(min-width: 720px) 33vw, 100vw")}'
                           f'<figcaption><b>{escape(r["name"])}</b> · {escape(r["structure"])}</figcaption></figure>')
    shown = [r for r in rooms if r.get("photo")]
    if shown:
        body += sec(head("객실", cfg.get("room_lead", "")) + f'<div class="gl">{"".join(room_card(r) for r in shown[:6])}</div>'
                    + f'<p class="rv" style="margin-top:30px"><a class="link" href="{base}/rooms.html">객실 {len(rooms)}곳 전부 보기</a></p>')

    rest = [s for s in cfg.get("photos", []) if s not in used][:6]
    if len(rest) >= 3:
        body += sec(head("둘러보기") + f'<div class="gl">{"".join(f"<figure class=" + chr(34) + "rv" + chr(34) + ">" + img(s, alt_of(s, "풍경"), "(min-width: 720px) 33vw, 100vw") + "</figure>" for s in rest[:len(rest) // 3 * 3])}</div>')

    ams = cfg.get("amenities", [])
    guide_short = "".join(f'<div><b>{escape(t)}</b><span>{lines(x)}</span></div>' for t, x in guide[:4])
    body += (f'<section id="rates"><div class="wrap">{head("이용 안내", ". ".join(x for x in (times, ", ".join(ams)) if x))}'
             + (f'<div class="extras rv">{guide_short}</div>' if guide_short else "")
             + f'<p class="rv" style="margin-top:34px"><a class="link" href="{base}/guide.html">이용 안내 전체 보기</a></p>'
             + f'<div class="book rv" id="book"><div class="wrap">{book_html}</div></div></div></section>')
    if faq:
        body += sec(head("자주 묻는 질문") + f'<div class="faq rv">{faq_html(faq)}</div>')
    body += sec(f'<div class="way"><div class="rv"><h2>오시는 길</h2><p class="addr" style="margin-top:20px">{escape(addr)}</p>'
                f'<div class="maps"><a class="btn btn-line" href="{route_url}" target="_blank" rel="noopener">카카오맵 길찾기</a>'
                f'<a class="btn btn-line" href="{escape(naver_map)}" target="_blank" rel="noopener">네이버 지도</a></div>'
                + (f'<p class="small">{escape(cfg["parking"])}</p>' if cfg.get("parking") else "") + "</div>"
                + (f'<div class="rv"><p>{escape(cfg["way_detail"])}</p><p class="small" style="margin-top:14px"><a class="link" href="{base}/around.html">오시는 길 자세히</a></p></div>' if cfg.get("way_detail") else "<div></div>")
                + "</div>")

    business = {"@context": "https://schema.org", "@type": "LodgingBusiness", "name": name, "description": cfg.get("description") or name,
                "address": {"@type": "PostalAddress", "streetAddress": addr, "addressCountry": "KR"}, "image": og_image}
    if tel:
        business["telephone"] = "+82-" + phone.lstrip("0")
    if g.get("lat"):
        business["geo"] = {"@type": "GeoCoordinates", "latitude": g["lat"], "longitude": g["lng"]}
    for k, v in (("checkinTime", "checkin"), ("checkoutTime", "checkout")):
        if cfg.get(v):
            business[k] = cfg[v]
    if ams:
        business["amenityFeature"] = [{"@type": "LocationFeatureSpecification", "name": x, "value": True} for x in ams]
    if domain:
        business["url"] = domain + "/"
    if same_as:
        business["sameAs"] = same_as
    desc = cfg.get("description") or f"{name} — {addr}"
    page("index.html", f"{name} | {cfg.get('category', '')} {cfg.get('hero_label', '')}".strip(), desc, body,
         [business, faq_ld(faq)], og_title=f"{name}, {(cfg.get('tagline') or '').replace('|', ' ')}".rstrip(", "), preload=preload)

    # ── 객실 ─────────────────────────────────────────────────────────────
    rooms_html, gallery = "", []
    for r in rooms:
        pic = ""
        if r.get("photo"):
            pic = f'<button type="button" data-full="{base}/images/{r["photo"]}.webp" aria-label="{escape(r["name"])} 사진 크게 보기">{img(r["photo"], alt_of(r["photo"], r["name"] + " 객실"), "(min-width: 1024px) 60vw, 100vw")}</button>'
            gallery.append({"@type": "ImageObject", "contentUrl": f"{base}/images/{r['photo']}.webp", "name": f"{name} {r['name']}"})
        info = "".join(f"<p>{escape(x)}</p>" for x in (r.get("structure"), ("비품: " + r["facilities"]) if r.get("facilities") else "", r.get("note")) if x)
        rooms_html += f'<article class="room"><div class="info rv"><h2>{escape(r["name"])}</h2>{info}</div><div class="g rv">{pic}</div></article>'
    rbody = (f'<div class="page"><div class="wrap phead"><h1>객실 {len(rooms)}곳</h1><p class="lead">{escape(cfg.get("room_lead") or name + " 객실 구조와 비품을 사장님이 등록한 그대로 옮겼습니다.")}</p></div>'
             f'<div class="wrap" style="padding-bottom:clamp(80px,10vw,140px)"><div class="rooms">{rooms_html}</div>'
             f'<div class="book" style="border:1px solid var(--line)"><div class="wrap">{book_html}</div></div></div></div>')
    page("rooms.html", f"객실 | {name}", f"{name} 객실 {len(rooms)}곳의 구조, 넓이, 비품과 사진. " + ", ".join(r["name"] for r in rooms[:6]), rbody,
         [{"@context": "https://schema.org", "@type": "ImageGallery", "name": f"{name} 객실 사진", "url": f"{base}/rooms.html", "image": gallery}, crumbs("rooms.html", "객실")],
         extra='<dialog class="lb"><button type="button" aria-label="닫기">×</button><img src="" alt=""></dialog>', current="rooms.html")

    # ── 이용 안내 ─────────────────────────────────────────────────────────
    rules = cfg.get("rules", [])
    gbody = (f'<div class="page"><div class="wrap phead"><h1>이용 안내</h1><p class="lead">{escape(". ".join(x for x in (times, "요금은 날짜와 객실마다 달라 예약 화면에서 바로 확인됩니다" if book else "") if x))}</p></div>'
             + (f'<div class="book" id="book" style="border-top:1px solid var(--line)"><div class="wrap">{book_html}</div></div>' if book_html else "")
             + (sec(f'<div class="extras" style="max-width:46em">{"".join(f"<div><b>{escape(t)}</b><span>{lines(x)}</span></div>" for t, x in guide)}</div>') if guide else "")
             + (sec(head("이용 규칙") + f'<dl class="rules" style="max-width:46em">{"".join(f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>" for k, v in rules)}</dl>') if rules else "")
             + (sec(head("자주 묻는 질문") + f'<div class="faq">{faq_html(faq)}</div>') if faq else "") + "</div>")
    page("guide.html", f"이용 안내 | {name}", f"{name} 입실과 퇴실 시간, " + ", ".join(t for t, _ in guide[:5]) + " 안내.", gbody,
         [faq_ld(faq), crumbs("guide.html", "이용 안내")], current="guide.html")

    # ── 오시는 길 ─────────────────────────────────────────────────────────
    abody = (f'<div class="page"><div class="wrap phead"><h1>오시는 길</h1><p class="lead">{escape(addr)}{(" (지번 " + escape(a["jibun"]) + ")") if a.get("jibun") else ""}</p>'
             f'<div class="maps"><a class="btn btn-fill" href="{route_url}" target="_blank" rel="noopener">카카오맵 길찾기</a>'
             f'<a class="btn btn-line" href="{escape(naver_map)}" target="_blank" rel="noopener">네이버 지도</a></div></div>'
             + sec("".join(f"<p style=" + chr(34) + "max-width:40em;margin-bottom:14px" + chr(34) + f">{escape(x)}</p>" for x in (cfg.get("way_detail"), cfg.get("parking")) if x) or "<p>내비게이션에 상호나 도로명 주소를 넣으면 됩니다.</p>")
             + "</div>")
    page("around.html", f"오시는 길 | {name}", f"{name} 오시는 길. {addr}. {cfg.get('parking', '')}".strip(), abody,
         [{"@context": "https://schema.org", "@type": "WebPage", "name": f"{name} 오시는 길", "url": f"{base}/around.html"}, crumbs("around.html", "오시는 길")], current="around.html")

    # ── 소식 (계약 뒤 글해줌이 채운다) · 404 ────────────────────────────────
    page("blog.html", f"소식 | {name}", f"{name} 소식과 계절 안내 글을 올리는 곳입니다.",
         f'<div class="page"><div class="wrap phead"><h1>소식</h1><p class="lead">계절 소식과 묵기 전에 알아 두면 좋은 이야기를 올립니다.</p></div>'
         f'<section style="padding-top:0;border-top:0"><div class="wrap"><p>첫 글을 준비하고 있습니다.</p></div></section></div>',
         [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{name} 소식", "url": f"{base}/blog.html"}, crumbs("blog.html", "소식")], current="blog.html")
    page("404.html", f"페이지를 찾을 수 없습니다 | {name}", "주소가 바뀌었거나 잘못 적혔을 수 있습니다. 처음 화면에서 다시 찾아 주세요.",
         f'<div class="page"><div class="wrap phead"><h1>그 주소에는 페이지가 없습니다</h1><p class="lead">주소가 바뀌었거나 잘못 적혔을 수 있습니다.</p>'
         f'<div class="maps"><a class="btn btn-fill" href="{base}/">처음으로</a></div></div></div>', [])

    # ── llms.txt · robots · 기타 ──────────────────────────────────────────
    nl = "\n"
    (D / "llms.txt").write_text(f"""# {name}

> {cfg.get('llms_intro') or desc}

## 기본 정보
- 업종: {cfg.get('category', '')}
- 주소: {addr}{(' (지번 ' + a['jibun'] + ')') if a.get('jibun') else ''}
- 전화: {phone or '네이버 예약으로 문의'}
{('- ' + times) if times else ''}
- 객실: {len(rooms)}곳
- 시설: {', '.join(ams) or '-'}
- 네이버 플레이스: {cfg.get('place_url', '')}
{('- 네이버 예약: ' + book) if book else ''}

## 이용 안내 (사장님 등록 내용)
{nl.join(f"- {t}: {' / '.join(x.splitlines())}" for t, x in guide)}

## 객실
{nl.join(f"- {r['name']}: {r.get('structure', '')}" for r in rooms)}

## 자주 묻는 질문
{nl.join(f"- Q. {q}{nl}  A. {x}" for q, x in faq)}
""", encoding="utf-8")
    (D / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {domain}/sitemap.xml\n" if domain and not noindex else "")
                                  + (f"#DaumWebMasterTool:{cfg['daum_verification']}\n" if cfg.get("daum_verification") else ""),  # 다음 웹마스터도구 소유 확인
                                  encoding="utf-8")
    if domain and not noindex:
        urls = [f"{domain}/"] + [f"{domain}/{p}" for p, _ in MENU]
        (D / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                       + "".join(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    for f in S.iterdir():
        shutil.copy(f, D / f.name)
    keys = [k for k in U.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}", k.stem)]
    if not keys:   # IndexNow 키는 세대마다 하나 — 없으면 만든다(llms.txt·최종 수정일과 함께 모든 홈페이지 기본값, 11/17)
        k = os.urandom(16).hex()
        (U / f"{k}.txt").write_text(k, encoding="utf-8")
        keys = [U / f"{k}.txt"]
    shutil.copy(keys[0], D / keys[0].name)
    print(f"빌드 완료: {D} · 페이지 {len(MENU) + 2}개 · 객실 {len(rooms)} · 사진 {len(size)}장" + (" · 검색 막힘(noindex, 견본)" if noindex else ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())
