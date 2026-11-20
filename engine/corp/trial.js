// 무료 체험 세대 전용(11/20 대표님 "이름·전화·동의만 받고 2번까지, 체험판 워터마크"). config.json "tools_trial": true 인 세대만
// build.py 가 dist/tools/trial.js 로 넣고 도구 모든 쪽에 붙인다. 정식 세대엔 이 파일이 없어 도구 코드의 TrialGate 확인은 그냥 지나간다.
// 막는 것: 보고서 PDF 2건(같은 파일 다시 열기는 셈하지 않음) · 엑셀·영상 저장 · PPT 는 장마다 「체험판」 표시를 박아서 내보냄.
// ponytail: 2건 셈은 이 기기(localStorage). 기록을 지우면 입장 쿠키도 같이 지워져 다시 이름·전화를 넣어야 한다 — 그 자체가 새 신청.
(() => {
  const MAX = 2, KEY = "corp_trial_reports";
  const APPLY = "https://sotong-corp.pages.dev/?utm_source=trial&utm_medium=tool&utm_campaign=corp_trial#apply";
  const MARK = "체험판 · 실제 고객 미팅에 사용할 수 없습니다";
  const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
  const save = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* 저장이 막힌 브라우저는 셈 없이 */ } };

  const css = document.createElement("style");
  css.textContent = `
.tr-bar{position:sticky;top:0;z-index:60;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;justify-content:center;padding:9px 14px;background:#7f1d1d;color:#fff;font:600 14px/1.45 Pretendard,"Malgun Gothic",sans-serif;text-align:center}
.tr-bar a{color:#fde68a;font-weight:800;white-space:nowrap}
.tr-wm{position:fixed;inset:0;z-index:30;pointer-events:none;display:flex;align-items:center;justify-content:center;overflow:hidden}
.tr-wm span{transform:rotate(-24deg);font:900 clamp(40px,9vw,120px)/1 Pretendard,"Malgun Gothic",sans-serif;color:#7f1d1d;opacity:.06;white-space:nowrap}
.tr-dlg{border:0;border-radius:14px;padding:26px 24px;max-width:min(420px,90vw);font:15px/1.65 Pretendard,"Malgun Gothic",sans-serif;color:#0f172a}
.tr-dlg::backdrop{background:rgba(15,23,42,.55)}
.tr-dlg h2{margin:0 0 8px;font-size:18px}.tr-dlg p{margin:0 0 16px}
.tr-dlg .row{display:flex;gap:8px;flex-wrap:wrap}.tr-dlg a,.tr-dlg button{flex:1 1 140px;padding:11px 14px;border-radius:999px;font-weight:800;font-size:15px;text-align:center;text-decoration:none;cursor:pointer;font-family:inherit}
.tr-dlg a{background:#c9a35c;color:#0f172a;border:0}.tr-dlg button{background:#fff;border:1.5px solid #0f172a;color:#0f172a}`;
  document.head.appendChild(css);

  let bar;
  const paint = () => { if (bar) bar.firstChild.textContent = `🧪 무료 체험판 · 보고서 ${Math.min(read().length, MAX)}/${MAX}건 사용 · 저장한 PPT에는 「체험판」 표시가 들어가 실제 고객 미팅에는 쓸 수 없습니다`; };
  const mount = () => {
    bar = document.createElement("div"); bar.className = "tr-bar";
    bar.append(document.createElement("span"));
    const a = document.createElement("a"); a.href = APPLY; a.target = "_blank"; a.rel = "noopener"; a.textContent = "정식으로 쓰기 · 창립 멤버 신청 →";
    bar.append(a); document.body.prepend(bar); paint();
    const wm = document.createElement("div"); wm.className = "tr-wm"; wm.setAttribute("aria-hidden", "true");
    wm.innerHTML = "<span>체험판</span>"; document.body.append(wm);
  };
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);

  function tell(title, text) {
    const d = document.createElement("dialog"); d.className = "tr-dlg";
    d.innerHTML = `<h2></h2><p></p><div class="row"><a target="_blank" rel="noopener">창립 멤버 신청 →</a><button type="button">닫기</button></div>`;
    d.querySelector("h2").textContent = title; d.querySelector("p").textContent = text; d.querySelector("a").href = APPLY;
    d.querySelector("button").onclick = () => d.close();
    d.addEventListener("close", () => d.remove());
    document.body.append(d); d.showModal();
  }

  function stamp(sl) {   // 장마다 새 옵션 객체(pptxgenjs 는 옵션을 제자리에서 바꾼다)
    sl.addText(MARK, { x: "4%", y: "36%", w: "92%", h: "26%", fontSize: 30, bold: true, color: "B91C1C", transparency: 55, rotate: 342, align: "center", valign: "middle", fontFace: "Malgun Gothic" });
  }   // 아래쪽 작은 안내 줄은 뺐다 — 장마다 있는 원래 밑글씨와 겹쳤다(11/20 파워포인트로 그려 확인)
  let Wrapped;
  window.TrialGate = {
    async pdf(file) {
      const list = read(), fp = `${file.name}|${file.size}`;
      if (list.includes(fp)) return;
      if (list.length >= MAX) {
        tell(`체험 ${MAX}건을 모두 쓰셨습니다`, `무료 체험은 보고서 ${MAX}건까지입니다. 이미 넣어 본 보고서는 다시 열 수 있습니다. 계속 쓰시려면 창립 멤버로 신청해 주세요. 전화로 15분 화면 설명을 드립니다.`);
        throw new Error(`무료 체험은 보고서 ${MAX}건까지입니다. 이미 넣어 본 보고서는 다시 열 수 있습니다.`);
      }
      list.push(fp); save(list); paint();
    },
    block(kind) {
      tell(`체험판에서는 ${kind} 저장이 안 됩니다`, `브리핑·제안서 PPT는 장마다 「체험판」 표시를 넣어 받으실 수 있습니다. ${kind} 저장은 정식 버전에서 됩니다.`);
      return true;
    },
    pptxLib(P) {
      if (Wrapped && Wrapped.base === P) return Wrapped;
      Wrapped = class extends P {
        constructor(...a) {
          super(...a);
          const slides = [], add = this.addSlide.bind(this), write = this.writeFile.bind(this);
          this.addSlide = (...x) => { const s = add(...x); slides.push(s); return s; };
          this.writeFile = (o) => { slides.splice(0).forEach(stamp); return write(o); };   // 내용 위에 마지막으로 얹는다
        }
      };
      Wrapped.base = P;
      return Wrapped;
    },
  };
})();
