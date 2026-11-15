// 문의 추적 (지시서 6장). body[data-track]이 비어 있으면 전송 없이 폼 안내만 동작.
(function () {
  var base = document.body.dataset.track;

  function classifyReferrer() {
    var r = document.referrer;
    if (!r) return "direct";
    if (/naver|google|daum|bing|search|chatgpt|perplexity/i.test(r)) return "search";
    if (/kakao/i.test(r)) return "kakao";
    return "other";
  }

  function send(type, extra) {
    if (!base) return;
    var payload = Object.assign({
      type: type,
      path: location.pathname,
      source: classifyReferrer(),
      ts: new Date().toISOString()
    }, extra || {});
    navigator.sendBeacon(base + "/event", JSON.stringify(payload));
  }

  send("visit");

  document.querySelectorAll("[data-ev]").forEach(function (el) {
    el.addEventListener("click", function () { send(el.dataset.ev); });
  });

  var form = document.getElementById("inq-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = Object.fromEntries(new FormData(form));
      data.consent = data.consent === "on"; // 개인정보 수집 동의 여부를 기록으로 남긴다
      if (base) {
        fetch(base + "/inquiry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign(data, { source: classifyReferrer(), ts: new Date().toISOString() }))
        }).catch(function () {});
        send("form");
      } else {
        // ponytail: 추적 서버 미설정 시 문자 앱으로 대체, track_url 설정되면 자동으로 폼 접수로 전환
        var tel = document.querySelector('[data-ev="tel"]').getAttribute("href").replace("tel:", "");
        location.href = "sms:" + tel + "?body=" + encodeURIComponent("[홈페이지 문의] " + data.name + " / " + data.phone + " / " + (data.message || ""));
      }
      form.querySelector(".form-done").hidden = false;
      form.querySelector("button").disabled = true;
    });
  }
})();
