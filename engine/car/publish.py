# -*- coding: utf-8 -*-
"""글해줌이 보낸 글 한 편을 이 사이트에 올린다.

  글(제목·본문·사진) → content/<슬러그>.md + assets/posts/ → build.py → wrangler 배포

기존 홈페이지 채널(publisher_homepage.py)은 GitHub의 posts.json을 고쳐 밀어 넣고
GitHub Pages가 알아서 다시 짓는 구조다. 이 사이트는 GitHub이 없고 build.py가
직접 짓기 때문에 그 방식이 안 통한다. 대신 같은 흐름(글 넣기 → 다시 짓기 →
검색 배관 갱신 → 공개)을 이 구조에 맞춰 옮겼다.

사용법
  python publish.py --json 글.json      글해줌·다른 프로그램이 부를 때
  python publish.py --json 글.json --no-deploy   올리지 않고 글만 넣어 확인
  python publish.py --demo              샘플 글로 전 과정 시험

글.json 모양
  {"title": "...", "content": "...", "summary": "...",
   "tags": ["제천", "카니발"], "images": ["C:/.../1.jpg", ...]}
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))   # 'import build' 이 세대 폴더의 연결 파일이 아니라 엔진 build.py 를 잡게
import build  # noqa: E402

ROOT = CONTENT = POST_IMAGES = None   # 글을 올릴 세대 폴더 (use_unit 이 정한다)


def use_unit(path):
    global ROOT, CONTENT, POST_IMAGES
    ROOT = Path(path).resolve()
    CONTENT = ROOT / "content"
    POST_IMAGES = ROOT / "assets" / "posts"
    build.use_unit(ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def slugify(title):
    """제목 → 파일명. 한글은 주소에 그대로 쓰면 인코딩돼 길어지므로 날짜+번호로 간다.

    글 제목이 한글이라 로마자로 옮기면 뜻이 사라지고, 그대로 두면 주소가
    %EC%A0%9C... 로 늘어진다. 날짜 기반이면 짧고, 순서도 눈에 보인다.
    """
    today = date.today().isoformat()
    n = 1
    while (CONTENT / f"{today}-{n}.md").exists():
        n += 1
    return f"{today}-{n}"


def clean(text):
    """AI 원고에서 홈페이지에 필요 없는 부분을 걷어낸다.

    글해줌 원고는 여러 채널이 같이 쓰는 판본이라 해시태그·카드문구·이미지 마커가
    끝에 붙어 온다. publisher_homepage._text_to_html 이 걷어내는 것과 같은 것들이다.
    """
    text = (text or "").strip()
    text = re.sub(r"\[이미지[:：][^\]]*\]", "", text)
    text = re.sub(r"\n\s*해시태그\s*[:：][\s\S]*$", "", text)
    text = re.sub(r"\n(#\S+\s*)+$", "", text)
    text = re.sub(r"\n카드문구[:：]?\s*\n[\s\S]*$", "", text)
    return text.strip()


def place_images(body, image_names):
    """대표 사진은 맨 위, 나머지는 소제목마다 하나씩.

    소제목 '바로 밑'이 아니라 그 아래 첫 문단 '뒤'에 넣는다. 검색·AI가 뽑아가는
    것이 소제목 다음 첫 문장인데, 사진이 그 자리를 차지하면 밀려난다.
    (publisher_homepage._place_images 와 같은 판단)
    """
    if not image_names:
        return body
    imgs = [f"![]({'assets/posts/' + n})" for n in image_names]
    lines = body.split("\n")
    out = [imgs.pop(0), ""]

    after_heading = False
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            out.append(line)
            after_heading = True
            continue
        out.append(line)
        # 소제목 뒤 첫 문단이 끝난 자리
        if after_heading and s and not s.startswith(("#", "-", ">", "|")) and imgs:
            out += ["", imgs.pop(0)]
            after_heading = False
    return "\n".join(out)


def copy_images(paths, slug):
    """사진을 assets/posts/ 로 옮긴다. build.py가 assets를 통째로 배포에 싣는다.

    원본은 3~5MB짜리라 그대로 두면 폰에서 페이지가 느려진다. 가로 1200px로 줄인다.
    """
    if not paths:
        return []
    POST_IMAGES.mkdir(parents=True, exist_ok=True)
    names = []
    for i, p in enumerate(paths, 1):
        src = Path(p)
        if not src.exists():
            print(f"[건너뜀] 사진을 못 찾음: {p}")
            continue
        name = f"{slug}-{i}.jpg"
        try:
            from PIL import Image
            im = Image.open(src).convert("RGB")
            if im.width > 1200:
                im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
            im.save(POST_IMAGES / name, "JPEG", quality=82, optimize=True)
        except Exception:
            shutil.copy2(src, POST_IMAGES / name)   # PIL이 없거나 실패하면 원본 그대로
        names.append(name)
    return names


def write_post(title, content, summary, tags, image_paths):
    """content/<슬러그>.md 를 만든다. build.py가 읽는 형식 그대로."""
    CONTENT.mkdir(exist_ok=True)
    slug = slugify(title)
    body = place_images(clean(content), copy_images(image_paths, slug))

    # 설명문이 없으면 본문 첫 문단에서 뽑는다 (검색 결과에 뜨는 두 줄)
    if not summary:
        plain = re.sub(r"!\[.*?\]\(.*?\)", "", body)
        plain = re.sub(r"[#>|*-]", " ", plain)
        summary = re.sub(r"\s+", " ", plain).strip()[:150]

    # 제목·설명에 콜론이 있으면 build.py의 머리말 파서가 앞부분만 읽는다
    safe = lambda s: str(s).replace(":", " -").replace("\n", " ").strip()
    md = (f"---\ntitle: {safe(title)}\n"
          f"description: {safe(summary)}\n"
          f"date: {date.today().isoformat()}\n"
          f"tags: {safe(', '.join(tags or []))}\n---\n\n{body}\n")
    path = CONTENT / f"{slug}.md"
    path.write_text(md, encoding="utf-8")
    return slug, path


def run(cmd, label):
    print(f"[{label}] {' '.join(cmd[:3])} ...")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=False)
    if r.stdout:
        print(r.stdout[-1500:])
    if r.returncode != 0:
        print(r.stderr[-1500:])
    return r.returncode == 0


def git_mode():
    """실고객 사이트(관리 화면이 있는 GitHub 저장소)인가.

    그 경우 원본은 GitHub 하나다. 사장님이 관리 화면에서 고친 것도, 글해줌이 넣는 글도
    전부 저장소에 쌓이고 Actions가 짓는다. 여기서 Cloudflare로 따로 올리면 두 원본이
    서로를 덮어쓴다 (사이트맵 생성기 두 개 사고와 같은 모양).
    """
    if not (ROOT / ".git").exists():
        return False
    try:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool((cfg.get("admin_repo") or "").strip())


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def push_post(slug, title):
    """새 글만 커밋해 저장소에 올린다. 그사이 관리 화면 저장이 끼어들면 받아서 다시 올린다."""
    ok, out = git("add", *[p for p in ("content", "assets/posts") if (ROOT / p).exists()])  # 사진 없는 글은 assets/posts 가 없다
    if ok:
        ok, out = git("commit", "-m", f"글해줌: 새 글 — {title}")
    for _ in range(2):
        if not ok:
            break
        ok, out = git("push")
        if ok:
            return True, ""
        ok, out = git("pull", "--rebase", "--autostash")
    return False, out[-400:]


def publish(title, content, summary="", tags=None, images=None, deploy=True,
            project=None):
    """글 한 편을 넣고 사이트를 다시 지어 올린다. {"ok": bool, ...} 반환."""
    gitmode = git_mode()
    if gitmode and deploy:
        # 사장님이 관리 화면에서 고친 설정·글을 먼저 받아 온다. 못 받으면 올리지 않는다
        # (옛 설정으로 빌드한 점검 결과를 믿을 수 없다).
        ok, out = git("pull", "--rebase", "--autostash")
        if not ok:
            return {"ok": False, "error": f"저장소에서 최신 내용을 받지 못해 올리지 않았습니다: {out[-300:]}"}
    # 본문이 비면 올리지 않는다. 빈 페이지가 검색에 남으면 오히려 손해고,
    # 성공으로 기록되면 왜 빈지 아무도 모른 채 넘어간다.
    plain = re.sub(r"[#>|*\-\s]", "", clean(content) or "")
    if len(plain) < 100:
        return {"ok": False, "error": f"본문이 너무 짧아 올리지 않았습니다 (글자 수 {len(plain)})"}
    if not (title or "").strip():
        return {"ok": False, "error": "제목이 비어 있어 올리지 않았습니다"}

    slug, path = write_post(title, content, summary, tags, images)
    print(f"[글 넣음] {path.name}")

    # build.py를 같은 파이썬으로 불러 sitemap·광고점검까지 한 번에 돌린다
    build.WARNINGS.clear()
    try:
        result = build.main()
    except SystemExit as e:
        path.unlink(missing_ok=True)
        return {"ok": False, "error": f"빌드 실패로 글을 되돌렸습니다: {e}"}

    # 광고 표현 위반은 사람이 봐야 한다. 글은 남기되 올리지는 않는다.
    # content/ 에 남겨 두면 다음 글이 발행될 때 같이 올라가 버린다 → _보류/ 로 빼 둔다.
    if not result["ok"]:
        hold = ROOT / "_보류"
        hold.mkdir(exist_ok=True)
        shutil.move(str(path), hold / path.name)
        build.WARNINGS.clear()
        build.main()   # 걸린 글을 뺀 상태로 dist를 되돌려 둔다
        return {"ok": False, "slug": slug,
                "error": "광고 표현 점검에 걸려 올리지 않았습니다. "
                         f"글은 _보류/{path.name} 로 빼 두었습니다. 고친 뒤 content/ 로 옮겨 다시 올려주세요.",
                "warnings": result["warnings"]}

    if not deploy:
        return {"ok": True, "slug": slug, "deployed": False,
                "message": f"글 {slug} 추가·빌드 완료 (배포는 안 함)"}

    if gitmode:
        ok, err = push_post(slug, title)
        if not ok:
            return {"ok": False, "slug": slug,
                    "error": f"글은 들어갔으나 저장소에 올리지 못했습니다: {err}"}
        return {"ok": True, "slug": slug, "deployed": True,
                "message": f"발행 완료 — 글 {slug} · 저장소에 올림, 1~2분 뒤 홈페이지 반영 · 총 {result['posts']}편",
                "warnings": result["warnings"]}

    name = project or (ROOT.name)
    ok = run(["npx", "--yes", "wrangler", "pages", "deploy", "dist",
              f"--project-name={name}", "--commit-dirty=true"], "배포")
    if not ok:
        return {"ok": False, "slug": slug,
                "error": "글은 들어갔으나 배포에 실패했습니다. 다시 배포해주세요."}

    return {"ok": True, "slug": slug, "deployed": True,
            "message": f"발행 완료 — 글 {slug} · 총 {result['posts']}편 · sitemap 갱신됨",
            "warnings": result["warnings"]}


DEMO = {
    "title": "제천에서 전기차 보조금 신청할 때 순서",
    "content": """제천에서 전기차를 사려는 분들이 가장 많이 묻는 것이 보조금입니다.

## 신청은 언제부터 되나요

지자체 공고가 나와야 접수가 시작됩니다. 공고 전에는 신청 자체가 불가능합니다.

1. 지자체 공고 확인
2. 차량 계약과 지원 신청서 접수
3. 지자체 승인 후 출고·등록

## 예산이 끊기면 어떻게 되나요

접수 순서로 배정되기 때문에 늦으면 다음 해를 기다려야 합니다.

- 상반기에 소진되는 지역도 있습니다
- 대상자 확정 후에는 출고 기한이 있습니다

금액과 조건은 해마다, 지자체마다 달라집니다. 올해 기준 우리 지역 공고를
같이 확인해 드리겠습니다.""",
    "tags": ["제천", "전기차", "보조금"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="글 데이터 JSON 파일")
    ap.add_argument("--demo", action="store_true", help="샘플 글로 시험")
    ap.add_argument("--no-deploy", action="store_true", help="빌드까지만 하고 배포 안 함")
    ap.add_argument("--project", help="Cloudflare Pages 프로젝트 이름")
    ap.add_argument("--unit", help="세대 폴더 (세대 폴더의 publish.py 로 부르면 자동)")
    a = ap.parse_args()
    if a.unit:
        use_unit(a.unit)
    if ROOT is None:
        ap.error("--unit <세대 폴더> 가 필요합니다")

    if a.demo:
        data = DEMO
    elif a.json:
        data = json.loads(Path(a.json).read_text(encoding="utf-8"))
    else:
        ap.error("--json 또는 --demo 가 필요합니다")

    r = publish(data.get("title", ""), data.get("content", ""),
                data.get("summary", ""), data.get("tags"), data.get("images"),
                deploy=not a.no_deploy, project=a.project or data.get("project"))
    print()
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
