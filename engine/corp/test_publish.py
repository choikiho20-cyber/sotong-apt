# -*- coding: utf-8 -*-
"""글해줌 연결 A안(11/20) 자체검사 — Actions 한 번을 이 PC에서 그대로 흉내 낸다.
세대 저장소(demo-corp 사본) + _engine + 법인도구/web, 원격은 임시 맨 저장소. wrangler·gh 는 가짜라 실제 사이트는 안 건드린다.
실행: python -X utf8 test_publish.py  (엔진 publish.py·deploy.py·WORKFLOW 를 고치면 돌릴 것)"""
import json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

S = Path(__file__).resolve().parents[3]   # sotong-sites
T = Path(tempfile.mkdtemp(prefix="corp_publish_"))
ws = T / "ws"
sh = lambda cwd, *a, env=None: subprocess.run(list(a), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
git = lambda cwd, *a: sh(cwd, "git", "-c", "user.name=t", "-c", "user.email=t@t", *a)

shutil.copytree(S / "sotong-apt/units/demo-corp", ws, ignore=shutil.ignore_patterns("dist", "__pycache__"))
cfg = json.loads((ws / "config.json").read_text(encoding="utf-8"))
cfg.update(admin_repo="x/sim", pages_project="sim-dummy")
(ws / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
# 공격자(고객 관리 화면 열쇠·털린 글해줌 앱)가 세대 저장소에 심을 수 있는 것: 연결 파일 바꿔치기·표준 모듈 가로채기.
# Actions 는 엔진만 돌려야 하므로 이 파일들이 실행되면(PWNED_*) 실패다.
for f in ("build.py", "publish.py", "hashlib.py", "json.py"):
    (ws / f).write_text(f"open(r'{ws}/PWNED_{f}', 'w').write('x')\n", encoding="utf-8")
sys.path.insert(0, str(S / "sotong-apt/engine/corp"))
import deploy  # noqa
(ws / ".gitignore").write_text(deploy.GITIGNORE, encoding="utf-8")
shutil.copytree(S / "sotong-apt/engine", ws / "_engine/engine", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(S / "법인도구/web", ws / "법인도구/web")
shutil.copy2(S / "법인도구/leak_trace.py", ws / "법인도구/leak_trace.py")

git(T, "init", "--bare", "-b", "main", "remote.git")
git(ws, "init", "-b", "main"); git(ws, "add", "-A"); git(ws, "commit", "-m", "입주")
git(ws, "remote", "add", "origin", str(T / "remote.git")); assert git(ws, "push", "-u", "origin", "main").returncode == 0
tracked = git(ws, "ls-files").stdout
assert "_engine/" not in tracked and "법인도구/" not in tracked and "dist/" not in tracked, "gitignore 가 빌드 재료를 막지 못함"

# 글해줌이 넣는 것: 정상 1 · 심의 위반 1 · 너무 짧음 1 · 깨진 파일 1
body = ("법인세법 시행령 제44조 제4항은 임원 퇴직금을 손금에 넣을 수 있는 한도를 정합니다. "
        "정관에 지급 규정이 있으면 그 규정으로, 없으면 시행령이 정한 계산식으로 한도를 봅니다. ") * 3
(ws / "inbox").mkdir()
(ws / "inbox/a.json").write_text(json.dumps({"title": "임원 퇴직금 한도는 정관에서 시작합니다: 시행령 제44조 정리",
    "content": f"## 정관 규정이 먼저입니다\n\n{body} <script>alert(1)</script>\n\n## 규정이 없으면\n\n{body}\n\n해시태그: #법인 #퇴직금",
    "keywords": ["임원 퇴직금", "정관<b>"]}, ensure_ascii=False), encoding="utf-8")
(ws / "inbox/b.json").write_text(json.dumps({"title": "가지급금 정리", "content": f"{body}\n\n저희가 절세 컨설팅을 해 드립니다."},
                                            ensure_ascii=False), encoding="utf-8")
(ws / "inbox/c.json").write_text(json.dumps({"title": "짧은 글", "content": "짧다"}, ensure_ascii=False), encoding="utf-8")
(ws / "inbox/d.json").write_text("{깨진", encoding="utf-8")
git(ws, "add", "-A"); git(ws, "commit", "-m", "글해줌 inbox"); git(ws, "push")

r = sh(ws, sys.executable, "-I", "-X", "utf8", "_engine/engine/corp/publish.py", "--inbox", "--unit", ".")
print(r.stdout[-900:], r.stderr[-400:])
today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
assert r.returncode == 1, "보류·거절이 있으면 1 (실패 메일)"
post = ws / "content" / f"{today}-1.md"
assert post.exists(), "정상 글이 content 로"
t = post.read_text(encoding="utf-8")
assert "해시태그" not in t and t.startswith("---\ntitle: 임원 퇴직금 한도는 정관에서 시작합니다: 시행령 제44조 정리\n"), t[:200]
assert len(list((ws / "_보류").glob("*.md"))) == 1 and len(list((ws / "_보류").glob("*.점검.txt"))) == 1, "위반 글은 _보류"
assert not list((ws / "inbox").glob("*.json")), "inbox 비워짐"
remote = sh(T, "git", "-c", "core.quotePath=false", "--git-dir", "remote.git", "ls-tree", "-r", "main", "--name-only").stdout
assert f"content/{today}-1.md" in remote and f"_보류/{today}-2.md" in remote and "inbox/a.json" not in remote, remote[-500:]
print("A 통과 — inbox 4편: 발행 1·보류 1·거절 2, 원격 저장소에 되올림, 실패 코드 1")

# 같은 실행을 한 번 더: 비어 있으면 0, 커밋 없음
r = sh(ws, sys.executable, "-I", "-X", "utf8", "_engine/engine/corp/publish.py", "--inbox", "--unit", ".")
assert r.returncode == 0 and "비어 있음" in r.stdout
print("B 통과 — 빈 inbox 는 조용히 0")

# deploy.py . (Actions 모드): 짓기 → 도구 문 검사 → wrangler(가짜) — 실제 사이트는 안 건드림
fake = T / "bin"; fake.mkdir()
(fake / "npx.cmd").write_text("@echo fake %*\r\n@exit /b 0\r\n", encoding="ascii")
env = {**os.environ, "PATH": f"{fake};{os.environ['PATH']}", "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "x/sim-dummy", "RUNNER_TEMP": str(T), "USERPROFILE": str(T / "home"), "HOME": str(T / "home")}
r = sh(ws, sys.executable, "-X", "utf8", "_engine/engine/corp/deploy.py", ".", env=env)
print(r.stdout[-700:], r.stderr[-400:])
assert r.returncode == 0 and "--project-name=sim-dummy --branch=main" in r.stdout
assert (ws / "dist" / "posts" / f"{today}-1.html").exists(), "새 글 페이지가 지어짐"
assert f"/posts/{today}-1<" in (ws / "dist" / "sitemap.xml").read_text(encoding="utf-8"), "사이트맵에 새 글"
page = (ws / "dist" / "posts" / f"{today}-1.html").read_text(encoding="utf-8")
assert "<script>alert" not in page and "&lt;script>alert" in page and "정관<b>" not in page, "밖에서 온 태그가 글자로"
print("C 통과 — Actions 모드 deploy.py . : 짓기·도구 문 검사·올리기 명령까지, 새 글이 사이트맵에")

# deploy.py <세대> 를 이 PC에서 치면 실고객(admin_repo)은 이 PC 사본을 올리지 않고 저장소에 다시 짓기만 부탁
env2 = {**env}; env2.pop("GITHUB_ACTIONS")
(fake / "gh.cmd").write_text("@echo fakegh %*\r\n@exit /b 0\r\n", encoding="ascii")
r = sh(ws, sys.executable, "-X", "utf8", "_engine/engine/corp/deploy.py", ".", env=env2)
assert "저장소에 다시 짓기 요청" in r.stdout and "pages deploy" not in r.stdout, r.stdout[-400:]
print("D 통과 — 이 PC에서는 실고객 세대를 직접 올리지 않음")

# E 고객·앱이 config 의 올릴 곳을 남의 프로젝트로 바꿔도 Actions 는 저장소 이름으로 고정 — 올리지 않는다
cfg = json.loads((ws / "config.json").read_text(encoding="utf-8")); cfg["pages_project"] = "bizsample"
(ws / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
r = sh(ws, sys.executable, "-I", "-X", "utf8", "_engine/engine/corp/deploy.py", ".", env=env)
assert r.returncode and "남의 사이트" in (r.stdout + r.stderr) and "pages deploy" not in r.stdout, r.stdout[-300:]
assert not list(ws.glob("PWNED_*")), f"세대 저장소 코드가 실행됨: {[p.name for p in ws.glob('PWNED_*')]}"
print("E 통과 — 올릴 곳 바꿔치기 거부 · 저장소에 심은 build.py/publish.py/hashlib.py/json.py 한 번도 안 돎")
shutil.rmtree(T, ignore_errors=True)
