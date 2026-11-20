/* ClipForge phone wall: columns of phone-shaped clips that glide up and down, used on the front page and the sign-in page.
   Some phones play the real demo clips; the others are drawn here (a gaming facecam, a podcast, big captions).
   It is decoration only: hidden from screen readers, paused while off screen, and still for people who turn motion off.
   Usage: PeakPhones(element, {cols: 3}). The phone size, gap, speed and tilt come from the CSS settings --pw, --gap, --dur and --tilt;
   the defaults here never win over a page's own. */
(function () {
  const CSS = `
:where(.cf-wall){--pw:170px;--gap:16px;--dur:48s;--tilt:-7deg;--cf-frame:#1C1B19;position:relative}
.cf-wall{overflow:hidden;
  -webkit-mask-image:linear-gradient(to bottom,transparent 0,#000 13%,#000 87%,transparent 100%);
  mask-image:linear-gradient(to bottom,transparent 0,#000 13%,#000 87%,transparent 100%)}
.cf-cols{position:absolute;left:0;right:0;top:-18%;display:flex;justify-content:center;align-items:flex-start;gap:var(--gap);
  transform:rotate(var(--tilt));transform-origin:50% 40%}
.cf-col{display:flex;flex-direction:column;gap:var(--gap);flex:none;animation:cf-up var(--dur) linear infinite;will-change:transform}
.cf-col.down{animation-direction:reverse}
.cf-col:nth-child(even){margin-top:calc(var(--pw) * -.7)}
@keyframes cf-up{to{transform:translateY(calc(-50% - var(--gap) / 2))}}
.cf-off .cf-col,.cf-off .cf-ph *{animation-play-state:paused!important}
.cf-ph{position:relative;flex:none;width:var(--pw);aspect-ratio:9/16;box-sizing:border-box;border-radius:calc(var(--pw) * .15);
  background:var(--cf-frame);border:calc(var(--pw) * .032) solid var(--cf-frame);overflow:hidden;isolation:isolate;
  font-family:"Inter Tight",Inter,system-ui,sans-serif;line-height:1}
.cf-scr{position:absolute;inset:0;overflow:hidden;border-radius:calc(var(--pw) * .12);background:#2B2A27}
.cf-scr>img,.cf-scr>video{width:100%;height:100%;object-fit:cover;display:block}
.cf-notch{position:absolute;z-index:3;top:calc(var(--pw) * .04);left:50%;width:30%;height:calc(var(--pw) * .065);border-radius:999px;
  background:var(--cf-frame);transform:translateX(-50%)}
.cf-ai{position:absolute;z-index:3;top:calc(var(--pw) * .14);left:calc(var(--pw) * .06);display:flex;align-items:center;gap:calc(var(--pw) * .025);
  padding:calc(var(--pw) * .028) calc(var(--pw) * .05);border-radius:999px;background:#FFFDF9;color:#1C1B19;
  font-size:calc(var(--pw) * .06);font-weight:600}
.cf-ai b{color:#E4572E;font-weight:700}
.cf-plat{position:absolute;z-index:3;left:calc(var(--pw) * .06);bottom:calc(var(--pw) * .11);padding:calc(var(--pw) * .022) calc(var(--pw) * .045);
  border-radius:999px;background:rgba(28,27,25,.74);color:#F6F1E8;font-size:calc(var(--pw) * .055);font-weight:600}
.cf-bar{position:absolute;z-index:3;left:8%;right:8%;bottom:calc(var(--pw) * .06);height:calc(var(--pw) * .016);min-height:2px;border-radius:2px;
  background:rgba(255,255,255,.35);overflow:hidden}
.cf-bar i{display:block;height:100%;background:#fff;transform-origin:left;animation:cf-play var(--t,7s) linear infinite}
.cf-ph.lt .cf-bar{background:rgba(28,27,25,.16)}.cf-ph.lt .cf-bar i{background:#1C1B19}
@keyframes cf-play{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.cf-scan{position:absolute;z-index:2;left:0;right:0;top:0;height:22%;pointer-events:none;
  background:linear-gradient(to bottom,rgba(228,87,46,0),rgba(228,87,46,.22));border-bottom:2px solid #E4572E;animation:cf-scan 3.6s cubic-bezier(.45,0,.55,1) infinite}
@keyframes cf-scan{0%{transform:translateY(-100%);opacity:0}12%{opacity:1}80%{opacity:1}100%{transform:translateY(460%);opacity:0}}
.cf-pill{position:absolute;z-index:2;left:50%;transform:translateX(-50%);white-space:nowrap;padding:calc(var(--pw) * .03) calc(var(--pw) * .05);
  border-radius:calc(var(--pw) * .025);background:#FFFDF9;color:#1C1B19;font:400 calc(var(--pw) * .1) Anton,Impact,sans-serif;
  letter-spacing:.02em;text-transform:uppercase}
.cf-pill em{font-style:normal;color:#E4572E}
.cf-game{position:absolute;inset:0;display:grid;grid-template-rows:1fr 1.55fr}
.cf-cam{position:relative;overflow:hidden;background:linear-gradient(135deg,#F3B79E,#E4572E)}
.cf-cam.v2{background:linear-gradient(135deg,#D3E3EC,#7FA6BF)}
.cf-face{position:absolute;left:50%;bottom:0;width:50%;height:80%;transform:translateX(-50%);opacity:.82;
  background:radial-gradient(circle at 50% 32%,#1C1B19 0 20%,transparent 21%),radial-gradient(ellipse 50% 42% at 50% 100%,#1C1B19 0 98%,transparent 100%);
  animation:cf-bob 2.6s ease-in-out infinite}
@keyframes cf-bob{50%{transform:translateX(-50%) translateY(4%) rotate(2deg)}}
.cf-gm{position:relative;background:repeating-linear-gradient(45deg,#3A3834 0 10px,#2B2A27 10px 20px);animation:cf-pan 5s linear infinite}
@keyframes cf-pan{to{background-position:56px 0}}
.cf-hp{position:absolute;left:8%;top:calc(var(--pw) * .1);width:34%;height:calc(var(--pw) * .035);border-radius:3px;background:#8BC34A}
.cf-map{position:absolute;right:8%;top:calc(var(--pw) * .08);width:22%;aspect-ratio:1;border-radius:4px;border:1.5px solid rgba(246,241,232,.6)}
.cf-cross{position:absolute;left:50%;top:55%;width:calc(var(--pw) * .12);aspect-ratio:1;transform:translate(-50%,-50%);
  background:linear-gradient(#F6F1E8,#F6F1E8) center/100% 1.5px no-repeat,linear-gradient(#F6F1E8,#F6F1E8) center/1.5px 100% no-repeat;opacity:.7}
.cf-game .cf-pill{top:39%}
.cf-pod{position:absolute;inset:0;background:linear-gradient(160deg,#E2DCEF,#D3E3EC)}
.cf-pod.v2{background:linear-gradient(160deg,#D8E2CF,#F3E3B3)}
.cf-two{position:absolute;top:26%;left:0;right:0;display:flex;justify-content:center;gap:10%}
.cf-two i{width:30%;aspect-ratio:1;border-radius:50%;background:#1C1B19;animation:cf-talk 1.8s ease-in-out infinite}
.cf-two i+i{background:#E4572E;animation-delay:-.9s}
@keyframes cf-talk{50%{transform:scale(1.08)}}
.cf-wave{position:absolute;left:12%;right:12%;top:52%;height:12%;display:flex;align-items:center;gap:4%}
.cf-wave i{flex:1;height:100%;border-radius:3px;background:rgba(28,27,25,.55);animation:cf-eq 1.2s ease-in-out infinite}
.cf-wave i:nth-child(3n){animation-delay:-.4s;background:#E4572E}.cf-wave i:nth-child(3n+1){animation-delay:-.8s}
@keyframes cf-eq{0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1)}}
.cf-sub{position:absolute;left:8%;right:8%;top:70%;text-align:center;color:#1C1B19;font-size:calc(var(--pw) * .085);font-weight:700;line-height:1.15}
.cf-sub em{font-style:normal;color:#E4572E}
.cf-big{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2%;
  font:400 calc(var(--pw) * .2) Anton,Impact,sans-serif;text-transform:uppercase;color:#1C1B19;letter-spacing:.01em}
.cf-big span{display:block;animation:cf-hot 2.7s infinite}
.cf-big span:nth-child(2){animation-delay:.9s}.cf-big span:nth-child(3){animation-delay:1.8s}
@keyframes cf-hot{0%,28%{color:#E4572E;transform:scale(1.14) rotate(-3deg)}34%,100%{color:#1C1B19;transform:none}}
@media (prefers-reduced-motion:reduce){.cf-wall *{animation:none!important}}`;

  // what each phone shows: v = a demo video, i = a demo picture, g = gaming facecam, pod = podcast, big = big captions
  const SCREENS = [
    {v: "hype", ai: 94, p: "Shorts", t: 6.5},
    {g: 1, cap: ["clutch", "1v4"], ai: 91, p: "TikTok", scan: 1},
    {i: "bounce", ai: 88, p: "Reels"},
    {pod: 1, cap: ["this changed", "everything"], ai: 86, p: "Shorts"},
    {big: ["kya", "scene", "hai"], bg: "#F3E3B3", ai: 89, p: "Reels"},
    {v: "clean", ai: 92, p: "Shorts", t: 6.5, scan: 1},
    {g: 2, cap: ["ace", "round"], ai: 95, p: "Shorts"},
    {i: "hype", ai: 90, p: "TikTok"},
    {big: ["wait", "for", "it"], bg: "#E2DCEF", ai: 87, p: "Shorts"},
    {pod: 2, cap: ["nobody talks", "about this"], ai: 93, p: "Reels", scan: 1},
    {v: "bounce", ai: 90, p: "TikTok", t: 6.5},
    {big: ["no", "way", "bro"], bg: "#D8E2CF", ai: 96, p: "Reels"},
  ];

  const media = (name, video) => video
    ? `<video src="/brand/demo-${name}.mp4?v=cf4" poster="/brand/demo-${name}.jpg?v=cf4" muted loop playsinline autoplay preload="metadata"></video>`
    : `<img src="/brand/demo-${name}.jpg?v=cf4" alt="" decoding="async">`;

  function phone(s, k, video) {
    let scr, light = false;
    if (s.v || s.i) scr = media(s.v || s.i, video && !!s.v);
    else if (s.g) scr = `<div class="cf-game"><div class="cf-cam${s.g === 2 ? " v2" : ""}"><i class="cf-face"></i></div>`
      + `<div class="cf-gm"><i class="cf-hp"></i><i class="cf-map"></i><i class="cf-cross"></i></div>`
      + `<b class="cf-pill">${s.cap[0]} <em>${s.cap[1]}</em></b></div>`;
    else if (s.pod) { light = true; scr = `<div class="cf-pod${s.pod === 2 ? " v2" : ""}"><div class="cf-two"><i></i><i></i></div>`
      + `<div class="cf-wave">${"<i></i>".repeat(9)}</div><b class="cf-sub">${s.cap[0]} <em>${s.cap[1]}</em></b></div>`; }
    else { light = true; scr = `<div class="cf-big" style="background:${s.bg}">${s.big.map(w => `<span>${w}</span>`).join("")}</div>`; }
    return `<div class="cf-ph${light ? " lt" : ""}"><div class="cf-scr">${scr}</div>${s.scan ? '<i class="cf-scan"></i>' : ""}`
      + `<i class="cf-notch"></i><span class="cf-ai">✦ AI <b>${s.ai}</b></span><span class="cf-plat">▶ ${s.p}</span>`
      + `<span class="cf-bar"><i style="--t:${s.t || 5 + (k % 4)}s;animation-delay:-${k * 1.3}s"></i></span></div>`;
  }

  window.PeakPhones = function (el, opt) {
    opt = opt || {};
    if (!el) return;
    if (!document.getElementById("cf-phones-css")) {
      const st = document.createElement("style"); st.id = "cf-phones-css"; st.textContent = CSS; document.head.appendChild(st);
    }
    const cols = opt.cols || 3, moving = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    let html = '<div class="cf-cols">';
    for (let j = 0; j < cols; j++) {
      const set = SCREENS.map((s, k) => [s, k]).filter(([, k]) => k % cols === j);
      // the column holds its phones twice so the loop never shows a gap; only the first copy plays video
      const a = set.map(([s, k]) => phone(s, k, moving)).join(""), b = set.map(([s, k]) => phone(s, k + 5, false)).join("");
      html += `<div class="cf-col${j % 2 ? " down" : ""}" style="animation-delay:-${j * 9}s">${a}${b}</div>`;
    }
    el.classList.add("cf-wall"); el.setAttribute("aria-hidden", "true");
    el.innerHTML = html + "</div>";
    const vids = [...el.querySelectorAll("video")];
    vids.forEach(v => { v.muted = true; v.play().catch(() => {}); });
    try {
      new IntersectionObserver(([e]) => {
        el.classList.toggle("cf-off", !e.isIntersecting);
        vids.forEach(v => e.isIntersecting ? v.play().catch(() => {}) : v.pause());
      }).observe(el);
    } catch {}
  };
})();
