// 장면별 고급 모션 (motion.css 와 짝). 글자는 전부 HTML 원문에 그대로 있고, 여기서는 보이는 방식만 바꾼다 —
// 검색·AI 로봇은 스크립트를 안 돌려도 같은 글자를 읽는다. 모션 최소화 설정이면 아무것도 움직이지 않는다.
(function () {
  var root = document.documentElement;
  // 모션 최소화 설정이거나 화면 감지(IntersectionObserver)가 없는 옛 브라우저면 모션 없이 전부 보이게
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) { root.classList.add('mx-still'); return; }
  root.classList.add('mx');
  // 안전망: 아래 어디서 오류가 나도 첫 화면 글은 3초 안에 반드시 보인다
  setTimeout(function () { var h = document.querySelector('header.hero'); if (h) h.classList.add('on'); }, 3000);
  var fine = matchMedia('(hover: hover) and (pointer: fine)').matches;

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function watch(els, cb, opt) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { cb(e.target); io.unobserve(e.target); } });
    }, opt || { threshold: 0.18, rootMargin: '0px 0px -6% 0px' });
    Array.prototype.forEach.call(els, function (el) { io.observe(el); });
  }

  // ── 제목: 단어 단위로 아래에서 차오른다 (읽는 글자는 aria-label 로 그대로)
  document.querySelectorAll('.sec-title, .feature-name').forEach(function (el) {
    var text = el.textContent.trim();
    if (!text || el.querySelector('*')) return;
    el.setAttribute('aria-label', text);
    el.innerHTML = text.split(/\s+/).map(function (w, i) {
      return '<span class="w" aria-hidden="true"><span style="--d:' + i * 70 + 'ms">' + esc(w) + '</span></span>';
    }).join(' ');
  });
  watch(document.querySelectorAll('.sec-title, .feature-name'), function (el) { el.classList.add('split-on'); });
  watch(document.querySelectorAll('.eyebrow, .stat, .principle, .feature, .offer'), function (el) { el.classList.add('in'); });
  watch(document.querySelectorAll('.steps'), function (el) {
    Array.prototype.forEach.call(el.querySelectorAll('.step-no'), function (n, i) { n.style.setProperty('--d', 300 + i * 260 + 'ms'); });
    el.classList.add('in');
  });
  // 차종 카드는 한 줄씩 물결처럼
  document.querySelectorAll('.model-grid').forEach(function (g) {
    Array.prototype.forEach.call(g.children, function (m, i) { m.style.setProperty('--d', (i % 4) * 90 + 'ms'); });
  });
  watch(document.querySelectorAll('.model'), function (el) { el.classList.add('in'); }, { threshold: 0.05 });
  // 검색으로 걸러진 카드(hidden)는 이미 '나타난' 상태로 둔다
  var finder = document.getElementById('model-search');
  if (finder) finder.addEventListener('input', function () {
    document.querySelectorAll('.model').forEach(function (m) { m.classList.add('in'); });
  });

  // ── 첫 화면: 이름 글자가 하나씩, 그 뒤 금빛이 흐른다 + 금가루
  var hero = document.querySelector('.hero');
  var name = document.querySelector('.hero-name');
  if (name && !name.querySelector('*')) {
    var t = name.textContent.trim();
    name.setAttribute('aria-label', t);
    name.innerHTML = Array.from(t).map(function (ch, i) {
      return ch === ' ' ? ' ' : '<span class="ch" aria-hidden="true" style="--d:' + (250 + i * 110) + 'ms">' + esc(ch) + '</span>';
    }).join('');
  }
  if (hero) {
    requestAnimationFrame(function () { requestAnimationFrame(function () { hero.classList.add('on'); }); });
    dust(hero);
  }

  // 마우스를 따라 첫 화면 사진이 살짝 움직인다(깊이감) — 마우스 화면만. 살짝 키워 둬서 가장자리가 안 보인다
  var media = hero && hero.querySelector('.hero-media');
  if (media && fine) {
    var tx = 0, ty = 0, cx = 0, cy = 0, moving = false;
    media.style.transform = 'scale(1.04)';
    hero.addEventListener('mousemove', function (e) {
      tx = (e.clientX / innerWidth - .5) * -24; ty = (e.clientY / innerHeight - .5) * -14;
      if (!moving) { moving = true; requestAnimationFrame(follow); }
    });
    var follow = function () {
      cx += (tx - cx) * .06; cy += (ty - cy) * .06;
      media.style.transform = 'translate3d(' + cx.toFixed(2) + 'px,' + cy.toFixed(2) + 'px,0) scale(1.04)';
      if (Math.abs(tx - cx) + Math.abs(ty - cy) > .05) requestAnimationFrame(follow); else moving = false;
    };
  }

  // ── 차종 이름 띠: 차종 칸 머리에 큰 이름이 끝없이 흐른다 (장식이라 읽기 도구에는 숨김 — 이름은 카드에 그대로 있다)
  var models = document.getElementById('models');
  var names = Array.prototype.map.call(document.querySelectorAll('.model[data-model]'), function (m) { return m.getAttribute('data-model'); });
  if (models && names.length) {
    var row = names.map(function (n, i) { return '<span' + (i % 2 ? '' : ' class="g"') + '>' + esc(n) + '</span>'; }).join('');
    var band = document.createElement('div');
    band.className = 'mx-marquee'; band.setAttribute('aria-hidden', 'true');
    band.innerHTML = '<div class="mx-track">' + row + row + '</div>';   // 두 벌 이어 붙여 -50% 에서 이음매 없이 돈다
    models.parentNode.insertBefore(band, models);
  }

  // ── 금빛 커서 고리 (마우스 화면만): 누를 수 있는 것 위에서 커진다
  if (fine) {
    var cur = document.createElement('i');
    cur.className = 'mx-cursor'; cur.setAttribute('aria-hidden', 'true');
    document.body.appendChild(cur);
    var mX = 0, mY = 0, pX = 0, pY = 0, chasing = false;
    addEventListener('mousemove', function (e) {
      mX = e.clientX; mY = e.clientY;
      if (!cur.classList.contains('on')) { pX = mX; pY = mY; cur.classList.add('on'); }
      cur.classList.toggle('big', !!(e.target.closest && e.target.closest('a, button, .model, summary')));
      if (!chasing) { chasing = true; requestAnimationFrame(chase); }
    }, { passive: true });
    document.documentElement.addEventListener('mouseleave', function () { cur.classList.remove('on'); });
    var chase = function () {
      pX += (mX - pX) * .2; pY += (mY - pY) * .2;
      cur.style.transform = 'translate3d(' + pX.toFixed(1) + 'px,' + pY.toFixed(1) + 'px,0)';
      if (Math.abs(mX - pX) + Math.abs(mY - pY) > .1) requestAnimationFrame(chase); else chasing = false;
    };
  }

  function dust(host) {
    var cv = document.createElement('canvas');
    cv.className = 'hero-dust';
    cv.setAttribute('aria-hidden', 'true');
    host.insertBefore(cv, host.querySelector('.hero-inner'));
    var ctx = cv.getContext("2d"), dpr = Math.min(devicePixelRatio || 1, 2), W, H, run = true, parts = [];
    function size() { W = cv.width = host.clientWidth * dpr; H = cv.height = host.clientHeight * dpr; cv.style.width = host.clientWidth + 'px'; cv.style.height = host.clientHeight + 'px'; }
    size(); addEventListener('resize', size, { passive: true });
    // 점이 아니라 가장자리가 번진 빛망울(보케) — 밝은 바탕에서 작은 점은 먼지처럼 보인다
    var n = innerWidth < 700 ? 16 : 30;
    for (var i = 0; i < n; i++) parts.push({ x: Math.random(), y: Math.random(), r: (Math.random() * 9 + 3) * dpr, v: Math.random() * .00028 + .0001, p: Math.random() * 6.28, s: Math.random() * .015 + .006 });
    var running = false;
    new IntersectionObserver(function (es) { run = es[0].isIntersecting; if (run && !running) loop(); }).observe(host);
    function loop() {
      if (!run) { running = false; return; }
      running = true;
      ctx.clearRect(0, 0, W, H);
      parts.forEach(function (q) {
        q.y -= q.v; q.p += q.s; if (q.y < -0.05) { q.y = 1.05; q.x = Math.random(); }
        var x = (q.x + Math.sin(q.p * .3) * .012) * W, y = q.y * H, g = ctx.createRadialGradient(x, y, 0, x, y, q.r);
        // 샴페인빛 심 → 금빛 → 투명. 테마 금색(채도 낮음)을 그대로 쓰면 밝은 바탕에서 회색 얼룩처럼 보인다
        g.addColorStop(0, 'rgba(255,238,196,.95)'); g.addColorStop(.45, 'rgba(214,174,84,.55)'); g.addColorStop(1, 'rgba(214,174,84,0)');
        ctx.globalAlpha = .18 + (Math.sin(q.p) + 1) * .16;
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, q.r, 0, 6.283); ctx.fill();
      });
      requestAnimationFrame(loop);
    }
  }

  // 첫 화면 글이 스크롤하면 살짝 떠오르며 옅어진다
  var inner = document.querySelector('.hero-inner');
  if (inner) {
    var q = false;
    addEventListener('scroll', function () {
      if (q) return; q = true;
      requestAnimationFrame(function () {
        q = false;
        var y = Math.min(scrollY, innerHeight);
        inner.style.transform = 'translate3d(0,' + (y * -0.18).toFixed(1) + 'px,0)';
        inner.style.opacity = (1 - y / innerHeight * 0.9).toFixed(3);
      });
    }, { passive: true });
  }

  // ── 계산기: 월 납입금이 굴러 올라가고, 원금·이자 비율 막대가 차오른다
  var calc = document.getElementById('calc-form');
  if (calc) {
    var out = calc.querySelector('.calc-out');
    var bar = document.createElement('div');
    bar.className = 'calc-bar'; bar.setAttribute('aria-hidden', 'true');
    bar.innerHTML = '<i class="p"></i><i class="r"></i>';
    var legend = document.createElement('p');
    legend.className = 'calc-legend'; legend.setAttribute('aria-hidden', 'true');
    legend.innerHTML = '<span><b style="background:var(--text)"></b>원금</span><span><b style="background:var(--gold)"></b>이자</span>';
    out.insertAdjacentElement('afterend', legend);
    out.insertAdjacentElement('afterend', bar);
    var shown = 0;
    var num = function (el) { return parseFloat(String(el.value).replace(/[^\d.]/g, '')); };
    calc.addEventListener('input', function () {
      var price = num(calc.price) * 1e4, down = (num(calc.down) || 0) * 1e4, n = +calc.months.value, rate = num(calc.rate), p = price - down;
      var strong = out.querySelector('strong');
      if (!(p > 0) || !isFinite(rate) || !strong) { bar.children[0].style.transform = bar.children[1].style.transform = 'scaleX(0)'; return; }
      var r = rate / 100 / 12, m = r ? p * r / (1 - Math.pow(1 + r, -n)) : p / n, total = m * n;
      bar.children[0].style.flex = p / total; bar.children[1].style.flex = (total - p) / total;
      bar.children[0].style.transform = bar.children[1].style.transform = 'scaleX(1)';
      var from = shown, to = Math.round(m), t0 = performance.now();
      shown = to;
      out.classList.add('bump'); setTimeout(function () { out.classList.remove('bump'); }, 350);
      (function step(t) {
        var k = Math.min((t - t0) / 700, 1), v = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)));
        strong.textContent = v.toLocaleString('ko-KR') + '원';
        if (k < 1) requestAnimationFrame(step);
      })(t0);
    });
  }

  // ── 자주 묻는 질문: 높이를 재서 부드럽게 열고 닫는다
  document.querySelectorAll('.faq').forEach(function (d) {
    var body = d.querySelector('p'), sum = d.querySelector('summary');
    if (!body || !sum) return;
    sum.addEventListener('click', function (e) {
      e.preventDefault();
      if (d.open) {
        body.animate([{ height: body.scrollHeight + 'px', opacity: 1 }, { height: '0px', opacity: 0 }], { duration: 380, easing: 'cubic-bezier(.4,0,.2,1)' })
          .onfinish = function () { d.open = false; };
      } else {
        d.open = true;
        body.animate([{ height: '0px', opacity: 0 }, { height: body.scrollHeight + 'px', opacity: 1 }], { duration: 480, easing: 'cubic-bezier(.16,1,.3,1)' });
      }
    });
  });

  // ── 문의: QR 스캔선
  var qr = document.querySelector('.qr-box');
  if (qr) { var s = document.createElement('i'); s.className = 'qr-scan'; s.setAttribute('aria-hidden', 'true'); qr.appendChild(s); }

  // ── 버튼이 손끝을 살짝 따라온다 (마우스 화면만)
  if (fine) document.querySelectorAll('.btn').forEach(function (b) {
    b.addEventListener('mousemove', function (e) {
      var r = b.getBoundingClientRect();
      b.style.transform = 'translate(' + ((e.clientX - r.left - r.width / 2) * .18).toFixed(1) + 'px,' + ((e.clientY - r.top - r.height / 2) * .28).toFixed(1) + 'px)';
    });
    b.addEventListener('mouseleave', function () { b.style.transform = ''; });
  });
})();
