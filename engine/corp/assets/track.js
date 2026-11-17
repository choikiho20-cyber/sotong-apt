// 방문·버튼·문의 기록 → 공용 서버(car-track). body[data-track]이 비어 있으면 기록 없이 문자 연결만 동작.
(function () {
  var base = document.body.dataset.track;
  var site = document.body.dataset.site || location.host; // github.io/저장소 처럼 경로까지
  var qs = new URLSearchParams(location.search);
  // 고객별 링크(?to=홍길동)로 연 사람 — 영업사원에게 '누가 봤는지' 알림이 간다
  var to = (qs.get("to") || "").slice(0, 40);

  function classifyReferrer() {
    if (qs.get("from") === "qr") return "qr";          // 명함·전시장 QR
    var r = document.referrer;
    if (!r) return "direct";
    if (/naver|google|daum|bing|search|chatgpt|perplexity/i.test(r)) return "search";
    if (/kakao/i.test(r)) return "kakao";
    return "other";
  }

  function send(type, extra) {
    if (!base) return;
    var payload = Object.assign({ site: site, type: type, source: classifyReferrer() }, extra || {});
    navigator.sendBeacon(base + "/event", new Blob([JSON.stringify(payload)], { type: "text/plain" }));
  }

  // 같은 사람이 새로고침할 때마다 '봤다' 알림이 쌓이지 않게 한 탭에 한 번만
  var seen = false;
  try { seen = sessionStorage.getItem("seen") === "1"; sessionStorage.setItem("seen", "1"); } catch (e) {}
  if (!seen) send("visit", to ? { to: to } : null);

  document.querySelectorAll("[data-ev]").forEach(function (el) {
    el.addEventListener("click", function () { send(el.dataset.ev); });
  });

  var form = document.getElementById("inq-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = Object.fromEntries(new FormData(form));
      data.consent = data.consent === "on"; // 개인정보 수집 동의 여부를 기록으로 남긴다
      // 숨겨진 칸(법인·시승 전용)은 빼고, 채운 칸만. 차종·날짜가 빠지면 되묻는 왕복이 생긴다.
      var LABEL = { inquiry_type: "구분", name: "성함", phone: "연락처", company: "회사", qty: "대수",
        deadline: "시기", visit_date: "희망 날짜", visit_time: "시간대", model: "차종", message: "내용" };
      var lines = ["[홈페이지 문의]"];
      Object.keys(LABEL).forEach(function (k) {
        var el = form.elements[k];
        if (!el || !data[k] || el.closest("[hidden]")) { delete data[k]; return; }
        lines.push(LABEL[k] + ": " + data[k]);
      });
      // 1) 서버 문의함에 보관(+텔레그램 알림)  2) 동시에 영업사원 폰으로 문자 —
      // 서버가 멈춰도 문의는 문자로 닿는다. 한국 손님에겐 문자 앱이 가장 확실한 길.
      if (base) {
        fetch(base + "/inquiry", {
          method: "POST", keepalive: true, headers: { "Content-Type": "text/plain" },
          body: JSON.stringify(Object.assign(data, { site: site, source: classifyReferrer(), to: to }))
        }).catch(function () {});
      }
      var tel = document.querySelector('[data-ev="tel"]').getAttribute("href").replace("tel:", "");
      location.href = "sms:" + tel + "?body=" + encodeURIComponent(lines.join("\n"));
      form.querySelector(".form-done").hidden = false;
      form.querySelector("button").disabled = true;
    });
  }
})();
