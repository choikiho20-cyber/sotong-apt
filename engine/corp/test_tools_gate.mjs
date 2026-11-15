// /tools/ 글해줌 구독 문(dist/_worker.js) 자체검사. 실행: python build.py 뒤  node test_tools_gate.mjs
// 글해줌 서버는 가짜(fetch 를 바꿔 끼움): A 로그인 ok → 쿠키  B 틀린 비밀번호 401  C 같은 날 쿠키 → 서버 안 묻고 통과
// D 날이 바뀐 쿠키 → key 로 재확인, 해지면 401  E 서버 죽음 → 401(닫힘)  F 위조 쿠키 401  G /tools 밖은 그대로
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
console.log('A~H 통과');
