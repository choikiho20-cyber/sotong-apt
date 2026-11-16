# -*- coding: utf-8 -*-
"""보안 머리글 A+ — 단지 엔진(corp·car) 공용. 11/17 대표님 "보안 뚫리면 끝장" (homepage-seo 7절, 표준 incar-nice-recruit SEC_HEADERS).

지은 dist 를 훑어 페이지 안에 직접 적힌 스크립트·on…= 의 지문(sha256)만 허용하고, 바깥은 단지가 넘겨준 주소만 허용해 dist/_headers 를 쓴다.
몰래 심은 코드는 지문이 달라 막힌다. 관리 화면은 경로별 예외(사이트 CSP 를 떼고 관리 전용 CSP·no-store·noindex) — 두 CSP 가 겹치면 관리 화면이 깨진다.
새 바깥 자원(지도·영상·글꼴·라이브러리)을 붙이면 그 단지 build 의 인자에 그 주소만 더하고, 견본에 올려 콘솔 CSP 막힘 0건·Observatory A+ 를 본다."""
import base64
import hashlib
import html
import re
import sys

COMMON = ("  Strict-Transport-Security: max-age=31536000; includeSubDomains\n"
          "  X-Content-Type-Options: nosniff\n"
          "  X-Frame-Options: DENY\n"
          "  Referrer-Policy: strict-origin-when-cross-origin\n"
          "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()\n"
          "  Cross-Origin-Opener-Policy: same-origin\n")


def _sha(s):
    return "'sha256-" + base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode() + "'"


def write(dist, *, script="", style="", font="", connect="", frame="", media="", wasm=False, worker=False,
          admin=(), admin_connect=""):
    """dist/_headers 를 쓴다. 반환: (페이지 안 스크립트 수, 인라인 이벤트 수)."""
    adm = {"/" + a.strip("/") for a in admin}
    scripts, handlers = set(), set()
    for f in dist.rglob("*.html"):
        if "/" + f.relative_to(dist).as_posix() in adm:
            continue
        h = f.read_text(encoding="utf-8")
        for m in re.finditer(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", h, re.S):
            if not re.search(r'type="application/(ld\+)?json"', m.group(1)):   # 데이터 칸은 실행되지 않는다
                scripts.add(m.group(2))
        handlers |= {html.unescape(v) for v in re.findall(r'\son[a-z]+="([^"]*)"', h)}
    hashes = " ".join(sorted(_sha(s) for s in scripts | handlers))
    parts = [
        "default-src 'self'",
        " ".join(x for x in ["script-src 'self'", "'unsafe-hashes'" if handlers else "", hashes,
                             "'wasm-unsafe-eval'" if wasm else "", script] if x),
        "worker-src 'self' blob:" if worker else "",
        f"style-src 'self' 'unsafe-inline' {style}".strip(),
        f"font-src 'self' {font}".strip(),
        "img-src 'self' data: blob:",
        f"media-src 'self' {media}".strip(),
        f"frame-src {frame}" if frame else "",
        f"connect-src 'self' {connect}".strip(),
        "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'", "upgrade-insecure-requests",
    ]
    csp = "; ".join(p for p in parts if p)
    if len(csp) > 1900:   # Cloudflare _headers 한 줄 한도 2,000자
        sys.exit(f"보안 머리글 CSP 가 {len(csp)}자 — 페이지 안 스크립트를 파일로 빼서 지문 수를 줄일 것")
    out = f"/*\n{COMMON}  Content-Security-Policy: {csp}\n"
    if adm:
        admin_csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' " + style + "; "
                     "font-src " + (font or "'self'") + "; img-src 'self' blob: data:; "
                     f"connect-src 'self' https://api.github.com {admin_connect}".strip() + "; "
                     "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        rule = (f"  ! Content-Security-Policy\n  Content-Security-Policy: {admin_csp}\n"
                "  Cache-Control: no-store\n  X-Robots-Tag: noindex, nofollow, noarchive\n")
        for a in sorted(adm | {a[:-5] for a in adm if a.endswith(".html")}):   # /admin.html 과 Cloudflare 가 넘기는 /admin 둘 다
            out += f"\n{a}\n{rule}"
    (dist / "_headers").write_text(out, encoding="utf-8")
    return len(scripts), len(handlers)
