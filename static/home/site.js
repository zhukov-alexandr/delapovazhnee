// Shared by the landing (templates/home.html) and the tickets page
// (templates/tickets.html). Loaded synchronously at the end of <body>, after
// the page has defined its own dictionary as window.DP_I18N.

// --- i18n: RU (default) / EN / 中文. Names are transliterated (Dela
// povazhnee, Urban, Ritmy…), not translated. Default RU content is inline in
// the HTML; the switcher swaps text + persists the choice across both pages. ---
(function () {
  var I18N = window.DP_I18N || {};
  var htmlLang = { ru: "ru", en: "en", zh: "zh-CN" };
  function apply(lang) {
    var t = I18N[lang] || I18N.ru || {};
    document.documentElement.lang = htmlLang[lang] || "ru";
    if (t.title) document.title = t.title;
    var md = document.querySelector('meta[name="description"]');
    if (md && t.meta_desc) md.setAttribute("content", t.meta_desc);
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var k = el.getAttribute("data-i18n"); if (t[k] != null) el.textContent = t[k];
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      var k = el.getAttribute("data-i18n-html"); if (t[k] != null) el.innerHTML = t[k];
    });
    document.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.getAttribute("data-i18n-attr").split(";").forEach(function (pair) {
        var i = pair.indexOf(":"), attr = pair.slice(0, i), k = pair.slice(i + 1);
        if (t[k] != null) el.setAttribute(attr, t[k]);
      });
    });
    // Links shown only for certain languages (e.g. TikTok in ru/en, NetEase/
    // Bilibili/Douyin in zh). data-lang-only is a space-separated lang list.
    document.querySelectorAll("[data-lang-only]").forEach(function (el) {
      el.hidden = el.getAttribute("data-lang-only").split(/\s+/).indexOf(lang) === -1;
    });
    document.querySelectorAll(".lang-btn").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-lang") === lang);
    });
    try { localStorage.setItem("dp_lang", lang); } catch (e) {}
  }
  var saved = null;
  try { saved = localStorage.getItem("dp_lang"); } catch (e) {}
  apply(saved && I18N[saved] ? saved : "ru");
  document.querySelectorAll(".lang-btn").forEach(function (b) {
    b.addEventListener("click", function () { apply(b.getAttribute("data-lang")); });
  });
})();

// Mobile nav toggle.
(function () {
  var nav = document.getElementById("nav");
  if (!nav) return;
  var toggle = nav.querySelector(".nav__toggle");
  toggle.addEventListener("click", function () {
    var open = nav.classList.toggle("nav--open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  nav.querySelectorAll(".nav__links a").forEach(function (a) {
    a.addEventListener("click", function () {
      nav.classList.remove("nav--open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
})();

// Propagate UTM params to outbound links (and to /tickets, /game: the tags
// then ride along to the ticket checkout from there).
(function () {
  var qs = window.location.search;
  if (!qs) return;
  var p = new URLSearchParams(qs);
  var tags = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
  var parts = [];
  tags.forEach(function (t) { if (p.has(t)) parts.push(t + "=" + encodeURIComponent(p.get(t))); });
  if (!parts.length) return;
  // The tickets page reads these back for the TicketsCloud checkout if its own
  // URL carries no tags (same key and shape as its inline passthrough script).
  try {
    var keep = {};
    ["utm_medium", "utm_campaign", "utm_content", "utm_term"].forEach(function (k) {
      if (p.get(k)) keep[k] = p.get(k).slice(0, 200);
    });
    if (Object.keys(keep).length) sessionStorage.setItem("dp_utm", JSON.stringify(keep));
  } catch (_) { /* private mode / storage off — the link below still carries them */ }
  var utm = parts.join("&");
  document.querySelectorAll("a[href]").forEach(function (a) {
    var h = a.getAttribute("href");
    if (!h || h[0] === "#" || h.indexOf("mailto:") === 0 || h.indexOf("tel:") === 0 || h.indexOf("utm_") !== -1) return;
    var hash = "";
    var i = h.indexOf("#");
    if (i !== -1) { hash = h.slice(i); h = h.slice(0, i); }   // keep #fragment last (wmcamp.ru/#concert, /#concerts)
    a.setAttribute("href", h + (h.indexOf("?") !== -1 ? "&" : "?") + utm + hash);
  });
})();
