// /tools/ 글해줌 구독 문(dist/_worker.js) 자체검사. 실행: python build.py 뒤  node test_tools_gate.mjs
// 글해줌 서버는 가짜(fetch 를 바꿔 끼움): A 로그인 ok → 쿠키  B 틀린 비밀번호 401  C 같은 날 쿠키 → 서버 안 묻고 통과
// D 날이 바뀐 쿠키 → key 로 재확인, 해지면 401  E 서버 죽음 → 401(닫힘)  F 위조 쿠키 401  G /tools 밖은 그대로
// N 관리 화면 들어가기(/admin/login·token·logout, 11/21): 글해줌 로그인 → 앱 열쇠(JWT RS256) → 30일 쿠키. 견본(ADMIN_REPO 없음)은 404
import assert from 'node:assert/strict';
// 세대 폴더에서 실행: node ../../engine/corp/test_tools_gate.mjs  (cwd 의 dist/_worker.js 를 검사)
import { pathToFileURL } from 'node:url';
const { default: worker } = await import(pathToFileURL(process.cwd() + '/dist/_worker.js').href);
const calls = [];
let serverReply = { status: 200, body: { ok: true } };
globalThis.fetch = async (url, init) => {
  calls.push(JSON.parse(init.body));
  if (serverReply === 'down') throw new Error('ECONNREFUSED');
  return { ok: serverReply.status < 400, json: async () => serverReply.body };
};
const env = { TOOLS_API_KEY: 'k1', GEULHAEJUM_URL: 'https://x', ASSETS: { fetch: async () => new Response('ASSET', { status: 200 }) } };
const req = (path, opt = {}) => new Request('https://site.test' + path, opt);
const post = (email, pw) => req('/tools/', { method: 'POST', body: new URLSearchParams({ email, pw }), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });

// A
let r = await worker.fetch(post('A@Test.kr', 'pw'), env);
assert.equal(r.status, 303);
const ck = r.headers.get('Set-Cookie'); assert.match(ck, /^tools_auth=a%40test.kr\|\d+\|[a-f0-9]{64}; Path=\/tools/);
assert.deepEqual(calls.at(-1), { email: 'a@test.kr', password: 'pw' });
const jar = ck.split(';')[0];
// B
serverReply = { status: 401, body: { ok: false, reason: '틀림' } };
r = await worker.fetch(post('a@test.kr', 'bad'), env); assert.equal(r.status, 401); assert.match(await r.text(), /틀림/);
// C 같은 날 쿠키: 서버에 안 묻는다
const n = calls.length;
r = await worker.fetch(req('/tools/corp/sim/', { headers: { Cookie: jar } }), env);
assert.equal(await r.text(), 'ASSET'); assert.equal(calls.length, n);
// D 어제 쿠키: key 로 재확인 → 해지면 401
const [e, day, sig] = jar.slice('tools_auth='.length).split('|');
const sha = async (s) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(x => x.toString(16).padStart(2, '0')).join('');
const old = `tools_auth=${e}|${day - 1}|${await sha('corp-tools-v3:k1:site.test:a@test.kr:' + (day - 1))}`;
serverReply = { status: 403, body: { ok: false, reason: '구독 끝' } };
r = await worker.fetch(req('/tools/', { headers: { Cookie: old } }), env);
assert.equal(r.status, 401); assert.match(await r.text(), /구독 끝/);
assert.deepEqual(calls.at(-1), { email: 'a@test.kr', key: 'k1' });
// D-2 살아 있으면 통과 + 새 쿠키
serverReply = { status: 200, body: { ok: true } };
r = await worker.fetch(req('/tools/', { headers: { Cookie: old } }), env);
assert.equal(await r.text(), 'ASSET'); assert.match(r.headers.get('Set-Cookie'), new RegExp(`\\|${day}\\|`));
// E 서버 죽음 → 닫힘
serverReply = 'down';
r = await worker.fetch(req('/tools/', { headers: { Cookie: old } }), env); assert.equal(r.status, 401);
r = await worker.fetch(post('a@test.kr', 'pw'), env); assert.equal(r.status, 401);
// F 위조 쿠키
serverReply = { status: 200, body: { ok: true } };
r = await worker.fetch(req('/tools/', { headers: { Cookie: `tools_auth=${e}|${day}|${'0'.repeat(64)}` } }), env); assert.equal(r.status, 401);
// F-2 주인 계정 지정
r = await worker.fetch(post('other@test.kr', 'pw'), { ...env, TOOLS_OWNER_EMAIL: 'Owner@test.kr ' }); assert.equal(r.status, 401);
r = await worker.fetch(post('owner@test.kr', 'pw'), { ...env, TOOLS_OWNER_EMAIL: 'Owner@test.kr ' }); assert.equal(r.status, 303);
// F-3 다른 사이트 쿠키(같은 API 키) → 401 / 주인 계정이 나중에 지정되면 옛 쿠키 → 401 (11/13 보안검토)
r = await worker.fetch(new Request('https://other.test/tools/', { headers: { Cookie: jar } }), env); assert.equal(r.status, 401);
r = await worker.fetch(req('/tools/', { headers: { Cookie: jar } }), { ...env, TOOLS_OWNER_EMAIL: 'owner@test.kr' }); assert.equal(r.status, 401);
r = await worker.fetch(req('/tools/', { headers: { Cookie: jar } }), { ...env, TOOLS_OWNER_EMAIL: 'a@test.kr' }); assert.equal(await r.text(), 'ASSET');
// B-2 빈 비밀번호 → 서버에 묻지도 않고 401 (key 모드로 새면 이메일만으로 들어온다)
{ const n2 = calls.length; r = await worker.fetch(post('a@test.kr', ''), env); assert.equal(r.status, 401); assert.equal(calls.length, n2); }
// G
r = await worker.fetch(req('/'), env); assert.equal(await r.text(), 'ASSET');
// H 비밀번호 모드(TOOLS_PASSWORD 있으면 글해줌 안 묻는다): 틀림 401 / 맞으면 쿠키 / 쿠키로 통과 / 위조 401 / 글해줌 쿠키는 안 통함
{ const envP = { ...env, TOOLS_PASSWORD: '1111' }; const n3 = calls.length;
  const postPw = (pw) => req('/tools/', { method: 'POST', body: new URLSearchParams({ pw }), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  r = await worker.fetch(postPw('0000'), envP); assert.equal(r.status, 401); assert.match(await r.text(), /틀렸습니다/);
  r = await worker.fetch(req('/tools/'), envP); assert.equal(r.status, 401); assert.doesNotMatch(await r.text(), /이메일/);
  r = await worker.fetch(postPw('1111'), envP); assert.equal(r.status, 303);
  const pj = r.headers.get('Set-Cookie').split(';')[0]; assert.match(pj, /^tools_auth=[a-f0-9]{64}$/);
  r = await worker.fetch(req('/tools/corp/sim/', { headers: { Cookie: pj } }), envP); assert.equal(await r.text(), 'ASSET');
  r = await worker.fetch(req('/tools/', { headers: { Cookie: 'tools_auth=' + '0'.repeat(64) } }), envP); assert.equal(r.status, 401);
  r = await worker.fetch(req('/tools/', { headers: { Cookie: jar } }), envP); assert.equal(r.status, 401);
  assert.equal(calls.length, n3, '비밀번호 모드는 글해줌 서버를 부르지 않는다'); }
// I 대입 막기(11/17): 같은 IP 5번 틀리면 맞는 비밀번호도 429, 다른 IP 는 그대로 들어간다
{ const envP = { ...env, TOOLS_PASSWORD: '1111' };
  const at = (ip, pw) => req('/tools/', { method: 'POST', body: new URLSearchParams({ pw }),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'CF-Connecting-IP': ip } });
  for (let i = 0; i < 5; i++) { r = await worker.fetch(at('9.9.9.9', 'x' + i), envP); assert.equal(r.status, 401); }
  r = await worker.fetch(at('9.9.9.9', '1111'), envP); assert.equal(r.status, 429); assert.match(await r.text(), /잠겼습니다/);
  r = await worker.fetch(at('8.8.8.8', '1111'), envP); assert.equal(r.status, 303); }
// J www.주소는 점 없는 주소로 301 (경로·물음표 그대로)
r = await worker.fetch(new Request('https://www.site.test/posts/a?x=1'), env);
assert.equal(r.status, 301); assert.equal(r.headers.get('Location'), 'https://site.test/posts/a?x=1');
// K 옛 임시 주소(프로젝트.pages.dev) → 정식 주소 301 — 정식 주소가 있는 세대만. 미리보기 주소(해시.프로젝트.pages.dev)는 그대로
const home = (await import('node:fs')).readFileSync(process.cwd() + '/dist/_worker.js', 'utf8').match(/const HOME = '([^']*)'/)[1];
r = await worker.fetch(new Request('https://proj.pages.dev/posts/a?x=1'), env);
if (home) { assert.equal(r.status, 301); assert.equal(r.headers.get('Location'), `https://${home}/posts/a?x=1`); }
else assert.equal(await r.text(), 'ASSET');
r = await worker.fetch(new Request('https://ab12cd34.proj.pages.dev/posts/a'), env);
assert.equal(await r.text(), 'ASSET');
console.log('A~K 통과' + (home ? ` (정식 주소 ${home})` : ' (임시 주소 세대 — 넘김 없음)'));
// L 무료 체험 문(11/20): 쿠키 없으면 이름·전화·동의 폼 — 신청 서버(/trial)로 바로 보내고, 사이트·UTM 숨은 칸, CSP form-action 은 그 서버만
{ const envT = { ...env, TOOLS_TRIAL_SECRET: 's3cret', TRIAL_TRACK_URL: 'https://track.test' };
  r = await worker.fetch(req('/tools/?utm_source=meta&utm_content=%22%3E%3Cb%3E'), envT);
  assert.equal(r.status, 401); const h = await r.text();
  assert.match(h, /action="https:\/\/track\.test\/trial"/); assert.match(h, /name="site" value="site\.test"/);
  assert.match(h, /name="utm_content" value="&quot;&gt;&lt;b&gt;"/);          // 주소 꼬리표는 글자로만(태그 끼워넣기 막힘)
  assert.match(h, /name="consent" required/); assert.match(h, /무료 체험 시작/); assert.doesNotMatch(h, /설계사/);
  assert.match(r.headers.get('Content-Security-Policy'), /form-action 'self' https:\/\/track\.test;/);   // 'self' = 서버가 돌려보내는 길(빠지면 크롬이 막음)
  // 입장표: 서버와 같은 서명이면 7일 쿠키 → 도구, 지난 표·위조 표·다른 사이트 표는 다시 문
  const hm = async (k, m) => { const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(k), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    return [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(m)))].map(x => x.toString(16).padStart(2, '0')).join(''); };
  const exp = Date.now() + 60000;
  r = await worker.fetch(req(`/tools/enter?t=${exp}.${await hm('s3cret', 'site.test|' + exp)}`), envT);
  assert.equal(r.status, 303); assert.equal(r.headers.get('Location'), '/tools/corp/');
  const tj = r.headers.get('Set-Cookie'); assert.match(tj, /Max-Age=604800; HttpOnly; Secure/);
  r = await worker.fetch(req('/tools/corp/', { headers: { Cookie: tj.split(';')[0] } }), envT); assert.equal(await r.text(), 'ASSET');
  const old = Date.now() - 1;
  r = await worker.fetch(req(`/tools/enter?t=${old}.${await hm('s3cret', 'site.test|' + old)}`), envT); assert.equal(r.status, 401); assert.match(await r.text(), /입장표가 지났습니다/);
  r = await worker.fetch(req(`/tools/enter?t=${exp}.${await hm('other', 'site.test|' + exp)}`), envT); assert.equal(r.status, 401);
  r = await worker.fetch(req(`/tools/enter?t=${exp}.${await hm('s3cret', 'evil.test|' + exp)}`), envT); assert.equal(r.status, 401);
  r = await worker.fetch(req('/tools/corp/', { headers: { Cookie: jar } }), envT); assert.equal(r.status, 401);   // 구독 쿠키로 체험 세대 못 들어감
  r = await worker.fetch(req('/tools/?e=many'), envT); assert.match(await r.text(), /잠시 뒤 다시/); }
// M 비밀번호 문: '설계사' 문구 없음, 체험 링크는 TOOLS_TRIAL_URL 이 있는 사이트(견본)만
{ r = await worker.fetch(req('/tools/'), { ...env, TOOLS_PASSWORD: 'longpass1234' }); let h = await r.text();
  assert.doesNotMatch(h, /설계사/); assert.doesNotMatch(h, /무료로 체험/);
  r = await worker.fetch(req('/tools/'), { ...env, TOOLS_PASSWORD: 'longpass1234', TOOLS_TRIAL_URL: 'https://trial.test/tools/' }); h = await r.text();
  assert.match(h, /href="https:\/\/trial\.test\/tools\/"[^>]*>비밀번호가 없으신가요\? 무료로 체험해 보기/); }
console.log('L~M 통과 (무료 체험 문·견본 체험 링크)');

// N 관리 화면 들어가기(11/21 대표님 "원래 쓰던 비밀번호로"): 견본은 404. 실고객 세대는 글해줌 로그인 → 글해줌 앱 JWT 로 저장소 열쇠 → 30일 쿠키 → /admin/token 재발급
{ const src = (await import('node:fs')).readFileSync(process.cwd() + '/dist/_worker.js', 'utf8');
  const adminRepo = src.match(/const ADMIN_REPO = '([^']*)'/)[1];
  const nodeCrypto = await import('node:crypto');
  const { privateKey, publicKey } = nodeCrypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const envA = { ...env, TOOLS_OWNER_EMAIL: 'owner@test.kr', GH_APP_ID: '77', GH_APP_KEY: privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64') };
  const gh = [], geulFetch = globalThis.fetch;   // GitHub 도 가짜 — 글해줌 가짜는 그대로
  globalThis.fetch = async (url, init) => {
    if (!String(url).startsWith('https://api.github.com/')) return geulFetch(url, init);
    gh.push({ url: String(url), init });
    if (String(url).endsWith('/installation')) return { ok: true, status: 200, json: async () => ({ id: 123 }) };
    return { ok: true, status: 201, json: async () => ({ token: 'ghs_fake', expires_at: '2099-01-01T00:00:00Z' }) };
  };
  // 앞 검사들이 'local' IP 로 4번 틀려 놓았다 — 관리 문 검사는 다른 IP 로(잠금은 아래서 따로 본다)
  const jpost = (path, body, extra = {}) => req(path, { method: 'POST', body: JSON.stringify(body || {}), headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': '6.6.6.6', ...extra } });
  if (!adminRepo) {
    r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'pw' }), envA); assert.equal(r.status, 404);
    console.log('N 통과 (견본 세대 — 관리 로그인 문 없음)');
  } else {
    serverReply = { status: 200, body: { ok: true } };
    let n0 = calls.length;   // 주인 계정 미지정 → 글해줌에 묻지도 않고 닫힘(관리 화면엔 '구독자 누구나'가 없다)
    r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'pw' }), { ...envA, TOOLS_OWNER_EMAIL: '' }); assert.equal(r.status, 401); assert.equal(calls.length, n0);
    r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'pw' }, { 'Sec-Fetch-Site': 'cross-site' }), envA); assert.equal(r.status, 403);
    r = await worker.fetch(jpost('/admin/login', { email: 'other@test.kr', pw: 'pw' }), envA); assert.equal(r.status, 401); assert.match((await r.json()).reason, /연결된 글해줌 계정이 아닙니다/);
    r = await worker.fetch(jpost('/admin/login', { email: 'Owner@Test.kr', pw: 'pw' }), envA); assert.equal(r.status, 200);
    const j = await r.json(); assert.equal(j.token, 'ghs_fake'); assert.deepEqual(calls.at(-1), { email: 'owner@test.kr', password: 'pw' });
    assert.equal(gh[0].url, `https://api.github.com/repos/${adminRepo}/installation`);
    const jwt = gh[0].init.headers.Authorization.slice(7).split('.'), b64u = s => Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
    const claims = JSON.parse(b64u(jwt[1])); assert.equal(claims.iss, '77'); assert.ok(claims.exp - claims.iat <= 600, 'GitHub 은 10분 넘는 JWT 를 거절한다');
    assert.ok(nodeCrypto.verify('RSA-SHA256', Buffer.from(jwt[0] + '.' + jwt[1]), publicKey, b64u(jwt[2])), 'JWT 서명이 앱 키와 맞아야 한다');
    assert.equal(gh[1].url, 'https://api.github.com/app/installations/123/access_tokens');
    assert.deepEqual(JSON.parse(gh[1].init.body), { repositories: [adminRepo.split('/')[1]], permissions: { contents: 'write' } });
    const ac = r.headers.get('Set-Cookie'); assert.match(ac, /^admin_auth=owner%40test\.kr\|\d+\|[a-f0-9]{64}; Path=\/admin; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict$/);
    const aj = ac.split(';')[0];
    n0 = calls.length; r = await worker.fetch(jpost('/admin/token', null, { Cookie: aj }), envA); assert.equal(r.status, 200); assert.equal(calls.length, n0, '같은 날 쿠키는 글해줌에 안 묻는다');
    r = await worker.fetch(jpost('/admin/token', null, { Cookie: aj.replace(/[a-f0-9]{64}$/, '0'.repeat(64)) }), envA); assert.equal(r.status, 401);
    r = await worker.fetch(jpost('/admin/token', null, { Cookie: jar }), envA); assert.equal(r.status, 401, '도구 쿠키로는 관리 열쇠 못 받음');
    r = await worker.fetch(new Request('https://other.test/admin/token', { method: 'POST', headers: { Cookie: aj } }), envA); assert.equal(r.status, 401, '다른 사이트 쿠키');
    const [ae, ad] = aj.slice('admin_auth='.length).split('|');
    const oldA = `admin_auth=${ae}|${ad - 1}|${await sha('corp-admin-v1:k1:site.test:owner@test.kr:' + (ad - 1))}`;
    serverReply = { status: 403, body: { ok: false, reason: '구독 끝' } };
    r = await worker.fetch(jpost('/admin/token', null, { Cookie: oldA }), envA); assert.equal(r.status, 401); assert.deepEqual(calls.at(-1), { email: 'owner@test.kr', key: 'k1' });
    serverReply = { status: 200, body: { ok: true } };
    r = await worker.fetch(jpost('/admin/token', null, { Cookie: oldA }), envA); assert.equal(r.status, 200); assert.match(r.headers.get('Set-Cookie'), new RegExp(`\\|${ad}\\|`));
    r = await worker.fetch(jpost('/admin/logout'), envA); assert.match(r.headers.get('Set-Cookie'), /^admin_auth=\|0\|; Path=\/admin; Max-Age=0;/);
    serverReply = { status: 401, body: { ok: false, reason: '틀림' } };
    for (let i = 0; i < 5; i++) { r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'x' }, { 'CF-Connecting-IP': '7.7.7.7' }), envA); assert.equal(r.status, 401); }
    r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'x' }, { 'CF-Connecting-IP': '7.7.7.7' }), envA); assert.equal(r.status, 429);
    serverReply = { status: 200, body: { ok: true } };
    r = await worker.fetch(req('/admin/login'), envA); assert.equal(r.status, 405);
    r = await worker.fetch(req('/admin'), envA); assert.equal(await r.text(), 'ASSET');
    r = await worker.fetch(jpost('/admin/login', { email: 'owner@test.kr', pw: 'pw' }), { ...envA, GH_APP_KEY: '' }); assert.equal(r.status, 401); assert.match((await r.json()).reason, /GH_APP_KEY/);
    console.log(`N 통과 (관리 화면 글해줌 로그인 · 앱 열쇠 JWT · 30일 쿠키 · 잠금) — ${adminRepo}`);
  }
  globalThis.fetch = geulFetch;
}
