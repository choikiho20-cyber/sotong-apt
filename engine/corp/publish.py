# -*- coding: utf-8 -*-
"""글해줌 글 → 법인 세대 홈페이지 글 (11/20, 글해줌 연결 A안).

  글해줌 서버 ── inbox/<번호>.json 한 파일 ──▶ 세대 저장소(비공개) ── push ──▶ Actions
     ├ publish.py --inbox : content/<날짜>-<n>.md 로 옮기고 심의 자동점검, 걸리면 _보류/ → 저장소에 되올림
     └ deploy.py .        : 짓기 → 도구 문 검사 → Cloudflare → IndexNow
md 로 바꾸는 일을 여기 한 곳에만 둔다. 글해줌과 엔진이 각자 만들면 사이트맵 생성기 두 개 사고와 같은 모양이 된다.

inbox/<번호>.json (글해줌 ↔ 엔진 약속, 번호는 겹치지 않게 시각+임의값)
  {"title": "제목", "content": "마크다운 본문(## 소제목)", "summary": "검색 결과 두 줄(없으면 첫 문단)", "keywords": ["..."]}
  사진은 1판에서 받지 않는다 — 법인 글은 조문 정리 글이라 글자만(견본 7편도 그렇다).

  python -I engine/corp/publish.py --inbox --unit <세대>     inbox 전부 처리 (Actions). 보류·거절이 있으면 1 로 끝나 대표님께 실패 메일
  python engine/corp/publish.py --json 글.json --unit <세대>  한 편만 넣어 보기 (올리지 않음)
  세대 폴더에 연결 파일을 두지 않는다 — 세대 저장소 파일은 고객·글해줌이 쓸 수 있어 Actions 에서 실행하면 비밀값이 샌다.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))   # 'import build' 이 세대 폴더의 연결 파일이 아니라 엔진 build.py 를 잡게
import build  # noqa: E402

ROOT = None   # 글을 넣을 세대 폴더 (use_unit 이 정한다)
# 글 속 링크로 허용하는 주소: http(s) 또는 콜론·따옴표·공백 없는 상대 주소(기존 글의 jeonggwan.html 같은 것).
# 엔진 inline() 은 href 를 따옴표 안에 그대로 넣으므로 '"' 하나로 속성을 깨고 on…= 를 심을 수 있다(11/20 보안 검토). deploy.check_unit 도 이걸 쓴다.
# 상대 주소엔 '&'·'%' 를 빼 둔다 — 브라우저가 &#106avascript&#58… 를 javascript: 로 풀어 읽는다(11/20 보안 검토 3차).
SAFE_HREF = re.compile(r"https?://[^\s\"'<>()]+|[\w./#?=-]+")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def use_unit(path):
    global ROOT
    ROOT = Path(path).resolve()
    build.use_unit(ROOT)


def clean(text):
    """여러 채널이 같이 쓰는 글해줌 원고 끝의 해시태그·카드문구·사진 자리표시를 걷어낸다(자동차 단지 publish.clean 과 같은 기준)."""
    text = (text or "").strip()
    text = re.sub(r"\[이미지[:：][^\]]*\]", "", text)
    text = re.sub(r"\n\s*해시태그\s*[:：][\s\S]*$", "", text)
    text = re.sub(r"\n(#\S+\s*)+$", "", text)
    text = re.sub(r"\n카드문구[:：]?\s*\n[\s\S]*$", "", text)
    return text.strip()


def add(d):
    """글 한 편 → content/<날짜>-<n>.md. 심의 자동점검에 걸리면 _보류/ 로 빼고 점검표를 옆에 둔다. (상태, 이름) 반환."""
    # 머리말은 한 줄이어야 parse_post 가 읽는다. 엔진 마크다운 변환은 HTML 을 그대로 통과시키고 보안 머리글은 페이지 안 스크립트 지문을
    # 허용하므로, 밖에서 온 글의 '<' 는 글자로 바꿔 태그가 못 들어오게 한다(11/20 보안 검토). '>' 는 인용(>)이라 둔다.
    one = lambda s: re.sub(r"[\s\"<>]+", " ", str(s or "")).strip()   # 머리말 값은 화면 속성에도 들어간다 — 따옴표·꺾쇠 빼기
    title, body = one(d.get("title")), clean(d.get("content")).replace("<", "&lt;")
    body = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", lambda m: m.group(0) if SAFE_HREF.fullmatch(m.group(2)) else m.group(1), body)
    if not title or len(re.sub(r"[#>|*\-\s]", "", body)) < 100:
        return "거절", "제목이 없거나 본문이 100자 미만"   # 빈 페이지가 검색에 남으면 손해, 성공으로 적히면 아무도 모른다
    summary = one(d.get("summary")) or one(re.sub(r"[#>|*\-]", " ", body))[:150]
    keywords = one(", ".join(d.get("keywords") or d.get("tags") or []))
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()   # Actions 는 UTC — 한국 날짜로
    n = 1
    while any((ROOT / f / f"{today}-{n}.md").exists() for f in ("content", "_보류")):
        n += 1
    name = f"{today}-{n}.md"
    path = ROOT / "content" / name
    path.write_text(f"---\ntitle: {title}\ndescription: {summary}\ndate: {today}\nkeywords: {keywords}\n---\n\n{body}\n",
                    encoding="utf-8")
    checklist, ok = build.compliance_check([build.parse_post(path)], {})
    if ok:
        return "발행", name
    hold = ROOT / "_보류"
    hold.mkdir(exist_ok=True)
    shutil.move(str(path), hold / name)
    (hold / f"{name}.점검.txt").write_text(checklist, encoding="utf-8")
    return "보류", name


def git(*args):
    r = subprocess.run(["git", "-c", "user.name=sotong-apt", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                        *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def run_inbox():
    git("pull", "--rebase", "--autostash")   # 앞 실행이 되올린 글을 먼저 받는다(줄 서 있던 실행이 옛 커밋에서 출발할 수 있다)
    files = sorted((ROOT / "inbox").glob("*.json"))
    results = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            results.append((f.name, *add(d)))
            # 사진 칸은 아파트 공용 형식(11/20)에 있지만 법인 1판은 쓰지 않는다 — 같이 온 사진은 inbox 안 것만 치운다
            for img in d.get("images") or []:
                p = (ROOT / str(img)).resolve()
                if p.is_relative_to((ROOT / "inbox").resolve()) and p.is_file():
                    p.unlink()
        except (ValueError, AttributeError) as e:
            results.append((f.name, "거절", f"글 파일을 읽지 못함: {e}"))
        f.unlink()
    for src, state, what in results:
        print(f"[{state}] {src} → {what}")
    if not results:
        print("inbox 비어 있음")
        return 0
    titles = ", ".join(w for _, s, w in results if s == "발행")
    git("add", "-A", "inbox", "content", *(["_보류"] if (ROOT / "_보류").exists() else []))
    ok, out = git("commit", "-m", f"글해줌: 새 글 {len(results)}편 정리 — {titles or '발행 없음'}")
    for _ in range(3):
        if not ok:
            break
        ok, out = git("push")
        if ok:
            break
        ok, out = git("pull", "--rebase", "--autostash")
    if not ok:
        print(f"[!] 저장소에 되올리지 못함: {out[-300:]}")
        return 1
    return 1 if any(s != "발행" for _, s, _ in results) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", action="store_true", help="inbox/*.json 전부 처리 (Actions)")
    ap.add_argument("--json", help="글 한 편 넣어 보기")
    ap.add_argument("--unit", help="세대 폴더 (세대 폴더의 publish.py 로 부르면 자동)")
    a = ap.parse_args()
    if a.unit:
        use_unit(a.unit)
    if ROOT is None:
        ap.error("--unit <세대 폴더> 가 필요합니다")
    if a.inbox:
        sys.exit(run_inbox())
    if not a.json:
        ap.error("--inbox 또는 --json 이 필요합니다")
    state, what = add(json.loads(Path(a.json).read_text(encoding="utf-8")))
    print(f"[{state}] {what}")
    sys.exit(0 if state == "발행" else 1)


if __name__ == "__main__":
    main()
