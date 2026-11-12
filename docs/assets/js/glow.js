// Lights the page the way Afterglow lights a room: one theme at a time,
// cross-fading from colour to colour. Runs faster than the real light so
// visitors can see a theme in a few seconds.
(function () {
  "use strict";
  var themes = window.AFTERGLOW_THEMES || [];
  if (!themes.length) return;

  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var els = {
    colour: document.getElementById("now-colour"),
    theme: document.getElementById("now-theme"),
    next: document.getElementById("now-next"),
    buttons: Array.prototype.slice.call(document.querySelectorAll(".theme[data-key]"))
  };

  var current = themes[0];
  var index = 0;
  var timer = null;

  function cadence(t) {
    if (t.key === "fireplace") return 2200;               // flicker
    return Math.min(9000, Math.max(4000, t.interval_s * 1000 / 6));
  }

  function show(i, instant) {
    index = i;
    var c = current.colours[i];
    var fade = instant || reduced.matches ? 0 : Math.round(cadence(current) * 0.65);
    root.style.setProperty("--fade", fade + "ms");
    root.style.setProperty("--glow", c.hex);
    if (els.colour) els.colour.textContent = c.name;
    if (els.theme) els.theme.textContent = current.name;
    if (els.next) els.next.textContent = "On your light this changes every " + current.every + ".";
    els.buttons.forEach(function (b) {
      if (b.dataset.key !== current.key) return;
      b.querySelectorAll(".swatches span").forEach(function (s, n) {
        s.classList.toggle("on", n === i);
      });
    });
  }

  function nextIndex() {
    var n = current.colours.length;
    if (current.key === "fireplace") {
      var r = Math.floor(Math.random() * (n - 1));
      return r >= index ? r + 1 : r;
    }
    return (index + 1) % n;
  }

  function schedule() {
    clearTimeout(timer);
    if (reduced.matches || document.hidden) return;
    timer = setTimeout(function () {
      show(nextIndex());
      schedule();
    }, cadence(current));
  }

  function pick(key) {
    var t = themes.filter(function (x) { return x.key === key; })[0];
    if (!t) return;
    els.buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.key === key));
      if (b.dataset.key !== key) {
        b.querySelectorAll(".swatches span.on").forEach(function (s) { s.classList.remove("on"); });
      }
    });
    current = t;
    show(0, false);
    schedule();
  }

  els.buttons.forEach(function (b) {
    b.addEventListener("click", function () { pick(b.dataset.key); });
  });
  document.addEventListener("visibilitychange", schedule);
  if (reduced.addEventListener) reduced.addEventListener("change", schedule);

  show(0, true);
  schedule();
})();
