// Page boot: wires the session/analytics (ab.js), the game controller
// (game.js), audio (audio.js), and the start/HUD/game-over overlays together.
import { readSession, markVisited, createEmitter } from "./ab.js";
import { Game } from "./game.js";
import { createAudio } from "./audio.js";
import { getBest, updateBest, getChar, setChar } from "./prefs.js";
import { loadSprites } from "./sprites.js";
import { GAME, PRESAVE } from "./config.js";
import { LYRICS } from "./lyrics.js";

// localStorage key: JSON array of service ids already presaved (Task 26).
const PRESAVED_KEY = "dp_presaved";

function readPresaved(store) {
  try {
    const raw = store.getItem(PRESAVED_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function addPresaved(store, id) {
  const ids = readPresaved(store);
  if (!ids.includes(id)) ids.push(id);
  try { store.setItem(PRESAVED_KEY, JSON.stringify(ids)); } catch (_) { /* ignore */ }
  return ids;
}

// Server-tunable defaults (Task 21/23), used if GET /api/config fails.
const CONFIG_FALLBACK = { points_per_line: 5, speed_mult: 1.0 };

// Short WebAudio blip on catching a collectible. Optional/best-effort: any
// failure (no AudioContext, autoplay-blocked) is swallowed silently.
let catchAudioCtx = null;
function sfxCatch() {
  try {
    if (!catchAudioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      catchAudioCtx = new AC();
    }
    const c = catchAudioCtx;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "square";
    osc.frequency.value = 880;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(c.destination);
    const now = c.currentTime;
    osc.start(now);
    gain.gain.setValueAtTime(0.12, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.06);
    osc.stop(now + 0.06);
  } catch (_) { /* WebAudio unavailable — ignore */ }
}

// Short descending "hit" blip on losing a life (best-effort, same as sfxCatch).
function sfxHit() {
  try {
    if (!catchAudioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      catchAudioCtx = new AC();
    }
    const c = catchAudioCtx;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sawtooth";
    osc.connect(gain);
    gain.connect(c.destination);
    const now = c.currentTime;
    osc.frequency.setValueAtTime(330, now);
    osc.frequency.exponentialRampToValueAtTime(90, now + 0.18);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);
    osc.start(now);
    osc.stop(now + 0.2);
  } catch (_) { /* WebAudio unavailable — ignore */ }
}

// Run-cycle frame manifest: char <n> (1-based file names, 0-based indices) with
// <count> frames at /static/sprites/characters/char<n>_run_<f>.png.
function runFramesManifest(n, count) {
  const m = {};
  for (let f = 0; f < count; f++) {
    m[`char_${n - 1}_run_${f}`] = `/static/sprites/characters/char${n}_run_${f}.png`;
  }
  return m;
}

function boot() {
  // Drop-in PNGs auto-swap on reload; missing files silently keep procedural art.
  loadSprites({
    ...runFramesManifest(1, 6), // Кирилл — 6-frame run cycle
    char_0: "/static/sprites/characters/char1.png",
    char_1: "/static/sprites/characters/char2.png",
    char_2: "/static/sprites/characters/char3.png",
    char_3: "/static/sprites/characters/char4.png",
    item_0: "/static/sprites/items/item1.png",
    item_1: "/static/sprites/items/item2.png",
    item_2: "/static/sprites/items/item3.png",
    item_3: "/static/sprites/items/item4.png",
  });

  const root = document.documentElement;
  const session = readSession(root);
  const emit = createEmitter(session);

  if (markVisited(localStorage)) emit("visit", {});

  const hud = document.getElementById("hud");
  const scoreEl = document.getElementById("score");
  const finalScoreEl = document.getElementById("final-score");
  const startEl = document.getElementById("start");
  const overEl = document.getElementById("over");
  const playBtn = document.getElementById("play");
  const retryBtn = document.getElementById("retry");
  const muteBtn = document.getElementById("mute");
  const bestScoreEl = document.getElementById("best-score");
  const bestScoreOverEl = document.getElementById("best-score-over");
  const charTiles = Array.from(document.querySelectorAll(".char-tile"));
  const revealPopup = document.getElementById("reveal-popup");
  const revealLineEl = document.getElementById("reveal-line");
  const revealNextBtn = document.getElementById("reveal-next");
  const livesEl = document.getElementById("lives");
  const lifeLostEl = document.getElementById("life-lost");
  const livesLeftEl = document.getElementById("lives-left");
  const lifeLostScoreEl = document.getElementById("life-lost-score");
  const continueBtn = document.getElementById("continue");
  const leaderboardEl = document.getElementById("leaderboard");
  const leaderboardList = document.getElementById("leaderboard-list");
  const leaderboardClose = document.getElementById("leaderboard-close");
  const showScoresStart = document.getElementById("show-scores-start");
  const showScoresOver = document.getElementById("show-scores-over");
  const nameInput = document.getElementById("name-input");
  const saveScoreBtn = document.getElementById("save-score");
  const toMenuBtn = document.getElementById("to-menu");

  const audio = createAudio();

  // Removes the `pulse` class once its scale-up/down keyframe finishes, so a
  // later reveal can retrigger the same animation from a clean state.
  if (scoreEl) {
    scoreEl.addEventListener("animationend", () => scoreEl.classList.remove("pulse"));
  }

  // --- Character picker: 4 selectable tiles on the start overlay. Cosmetic
  // only — sets game.charIndex, no effect on physics. Persists via prefs.js. ---
  function selectChar(i) {
    setChar(localStorage, i);
    for (const tile of charTiles) {
      tile.classList.toggle("selected", Number(tile.dataset.char) === i);
    }
  }

  for (const tile of charTiles) {
    const idx = Number(tile.dataset.char);
    tile.addEventListener("click", () => {
      selectChar(idx);
      game.charIndex = idx;
    });
  }

  // --- Best score (session-persisted via localStorage; shown on both
  // overlays). Updated on every game over with the max seen so far. ---
  function renderBest() {
    const best = getBest(localStorage);
    if (bestScoreEl) bestScoreEl.textContent = String(best);
    if (bestScoreOverEl) bestScoreOverEl.textContent = String(best);
  }
  renderBest();

  // --- Lives (hearts): MAX_LIVES filled, spent ones dimmed. ---
  function renderLives(n) {
    if (!livesEl) return;
    livesEl.innerHTML = "";
    for (let i = 0; i < GAME.MAX_LIVES; i++) {
      const h = document.createElement("span");
      h.className = i < n ? "heart" : "heart lost";
      h.textContent = "♥";
      livesEl.appendChild(h);
    }
  }
  // "Осталась 1 жизнь" / "Осталось 2 жизни" / "Осталось 5 жизней".
  function livesLeftText(n) {
    if (n % 10 === 1 && n % 100 !== 11) return `Осталась ${n} жизнь`;
    const d = n % 10, dd = n % 100;
    const form = (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) ? "жизни" : "жизней";
    return `Осталось ${n} ${form}`;
  }

  // --- CTA: build once from the <template>, mount by variant, and fire
  // cta_view exactly once when it actually becomes visible to the player. ---
  const ctaTpl = document.getElementById("cta-tpl");
  const ctaFrag = ctaTpl.content.cloneNode(true);
  const ctaRoot = ctaFrag.querySelector(".cta");
  // Cover image is static in the template; the presave link no longer
  // navigates — it opens the in-page presave modal (Task 26).
  const ctaLink = ctaFrag.querySelector(".presave");
  ctaLink.addEventListener("click", (e) => {
    e.preventDefault();
    emit("cta_click", { src: "button" });
    openPresaveModal();
  });

  const isVariantA = session.variant === "A";
  const ctaHost = document.getElementById(isVariantA ? "start-cta" : "over-cta");
  ctaHost.appendChild(ctaRoot);

  let ctaViewFired = false;
  function fireCtaView() {
    if (ctaViewFired) return;
    ctaViewFired = true;
    emit("cta_view", {});
  }
  if (isVariantA) fireCtaView(); // visible immediately on the start overlay

  // --- Presave modal (Task 26): white "bandlink-style" card with one row per
  // streaming service. Shared between variants A/B — mounted once in the DOM. ---
  const presaveModal = document.getElementById("presave-modal");
  const presaveClose = document.getElementById("presave-close");
  const presaveServicesEl = document.getElementById("presave-services");

  function savedActionSpan() {
    const span = document.createElement("span");
    span.className = "el-link__action el-link__action_disabled";
    span.title = "Релиз автоматически добавится в раздел Коллекция";
    span.textContent = "Сохранено";
    return span;
  }

  function markRowSaved(id) {
    const row = presaveServicesEl.querySelector(`li[data-service="${id}"]`);
    if (!row) return;
    const action = row.querySelector(".el-link__action");
    if (action) action.replaceWith(savedActionSpan());
  }

  // Our return URL — band.link redirects the popup here after a save; the page
  // logs presave_done and postMessages back so the row flips to «Сохранено».
  // Path params (no query!): band.link appends its own "?…Presaved=<upc>" success
  // marker with a literal "?", which would corrupt a URL that already had a query.
  function presaveReturnUrl(id) {
    return location.origin + "/presave/return/" + id + "/" + session.sid + "/" + session.variant;
  }

  // These resolve correctly through band.link's save-presave gateway AND honor
  // our redirectUrl. Spotify/Apple fall back to a Yandex login through the
  // gateway (so they're built directly below). КИОН/mts finalizes only when
  // redirectUrl is band.link's OWN smartlink domain (ERROR_1009 otherwise), so
  // it's a plain external link to the original page — no in-game detection.
  const GATEWAY_SERVICES = new Set(["yandex", "vkmusic"]);

  // Opens the correct presave flow for one service in a popup. No "noopener" on
  // the detected flows: the /presave/return popup needs window.opener to
  // postMessage back here.
  function openPresave(id) {
    const ret = presaveReturnUrl(id);

    if (GATEWAY_SERVICES.has(id)) {
      // "bandlink_id=undefined" mirrors the original page's request byte-for-byte.
      const url = "https://band.link/save-presave?type=" + id +
        "&bandlink_id=undefined&bandlink_hash=" + PRESAVE.HASH + "&upc=" + PRESAVE.UPC +
        "&redirectUrl=" + encodeURIComponent(ret);
      window.open(url, "_blank");
      return;
    }

    if (id === "mts") {
      // КИОН/МТС: band.link's finalize accepts only its own smartlink domain in
      // redirectUrl (external → ERROR_1009), so we can't route it back to us.
      // Just open the original band.link page — the presave completes there.
      window.open("https://dnkmusic.ru/devyatnadtsat", "_blank", "noopener");
      return;
    }

    if (id === "spotify") {
      // Direct Spotify OAuth with band.link's static client (same as the
      // original). band.link/spotify parses `state` (pipe-delimited) and, after
      // saving, redirects the popup to the 2nd field — our return URL.
      const u = new URL("https://accounts.spotify.com/authorize");
      u.searchParams.set("response_type", "code");
      u.searchParams.set("client_id", PRESAVE.SPOTIFY_CLIENT_ID);
      u.searchParams.set("scope", "user-follow-modify user-read-email user-library-modify");
      u.searchParams.set("redirect_uri", "https://band.link/spotify");
      u.searchParams.set("state", "undefined|" + ret + "|" + PRESAVE.UPC + "|" + PRESAVE.HASH);
      window.open(u.toString(), "_blank");
      return;
    }

    if (id === "applemusic") {
      // Apple MusicKit web-OAuth. The URL embeds a band.link developer token
      // that expires ~daily, so fetch a fresh one at click time (public
      // endpoint, permissive CORS). Open the popup synchronously first so the
      // async fetch doesn't trip the popup blocker.
      const win = window.open("about:blank", "_blank");
      fetch("https://api.band.link/apple/dev-token")
        .then((r) => r.json())
        .then(({ token }) => {
          const payload = JSON.stringify({
            thirdPartyIconURL: location.origin + "/static/sprites/19_2.jpg",
            thirdPartyName: location.host,
            thirdPartyToken: token,
          });
          const a = btoa(unescape(encodeURIComponent(payload)))
            .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
          const url = "https://authorize.music.apple.com/woa?a=" + encodeURIComponent(a) +
            "&referrer=" + encodeURIComponent(ret) + "&app=music&p=subscribe";
          if (win) win.location.href = url;
          else window.open(url, "_blank");
        })
        .catch(() => { if (win) win.close(); });
      return;
    }
  }

  // Build the 5 rows once; click opens the service's presave popup unless the
  // service is already saved (then the row is inert).
  for (const svc of PRESAVE.SERVICES) {
    const li = document.createElement("li");
    li.className = "bl-row";
    li.dataset.service = svc.id;

    const nameSpan = document.createElement("span");
    nameSpan.className = "bl-name";
    nameSpan.textContent = svc.name;

    const actionSpan = document.createElement("span");
    actionSpan.className = "el-link__action";
    actionSpan.textContent = "Пресейв";

    li.appendChild(nameSpan);
    li.appendChild(actionSpan);
    li.addEventListener("click", () => {
      if (li.querySelector(".el-link__action_disabled")) return; // already saved
      // КИОН is just an external link to the original page — no stats for it.
      if (svc.id !== "mts") emit("streaming_click", { service: svc.id });
      openPresave(svc.id);
    });
    presaveServicesEl.appendChild(li);
  }

  function openPresaveModal() {
    for (const id of readPresaved(localStorage)) markRowSaved(id);
    presaveModal.classList.remove("hidden");
    kbOpen(presaveModal, true);
  }

  presaveClose.addEventListener("click", () => {
    presaveModal.classList.add("hidden");
    kbClose();
  });

  const PRESAVE_IDS = new Set(PRESAVE.SERVICES.map((s) => s.id));
  window.addEventListener("message", (e) => {
    const data = e.data;
    if (!data || data.dp !== "presave_done" || !PRESAVE_IDS.has(data.service)) return;
    addPresaved(localStorage, data.service);
    markRowSaved(data.service);
    // Server already logged presave_done for this return — no emit here.
  });

  // The life-lost popup offers the same presave (cover + button → modal). It's a
  // separate CTA surface, tagged src:"life_lost" so it doesn't skew the
  // start-vs-gameover A/B click split; no cta_view is fired for it.
  const lifeLostCta = ctaTpl.content.cloneNode(true);
  lifeLostCta.querySelector(".presave").addEventListener("click", (e) => {
    e.preventDefault();
    emit("cta_click", { src: "life_lost" });
    openPresaveModal();
  });
  document.getElementById("life-lost-cta").appendChild(lifeLostCta.querySelector(".cta"));

  // --- Leaderboard (top 10): read-only modal opened from the start + game-over
  // overlays; scores are saved from the game-over name input and persisted
  // server-side (POST /api/score, GET /api/scores). ---
  const NAME_KEY = "dp_name";
  let lastGameScore = 0;

  function renderScores(list) {
    leaderboardList.innerHTML = "";
    if (!list.length) {
      const li = document.createElement("li");
      li.className = "lb-empty";
      li.textContent = "Пока пусто — стань первым!";
      leaderboardList.appendChild(li);
      return;
    }
    list.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = "lb-row";
      const rank = document.createElement("span");
      rank.className = "lb-rank";
      rank.textContent = String(i + 1);
      const nm = document.createElement("span");
      nm.className = "lb-name";
      nm.textContent = s.name; // textContent -> no HTML injection from stored names
      const sc = document.createElement("span");
      sc.className = "lb-score";
      sc.textContent = String(s.score);
      li.append(rank, nm, sc);
      leaderboardList.appendChild(li);
    });
  }

  function openLeaderboard() {
    fetch("/api/scores")
      .then((r) => r.json())
      .then((d) => renderScores(d.scores || []))
      .catch(() => renderScores([]));
    leaderboardEl.classList.remove("hidden");
    kbOpen(leaderboardEl, true);
  }

  showScoresStart.addEventListener("click", openLeaderboard);
  showScoresOver.addEventListener("click", openLeaderboard);
  leaderboardClose.addEventListener("click", () => { leaderboardEl.classList.add("hidden"); kbClose(); });

  saveScoreBtn.addEventListener("click", () => {
    const name = (nameInput.value || "").trim().slice(0, 24);
    saveScoreBtn.disabled = true;
    saveScoreBtn.textContent = "Сохранение…";
    fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, score: lastGameScore }),
    })
      .then((r) => {
        if (!r.ok) throw new Error("save failed");
        localStorage.setItem(NAME_KEY, name);
        saveScoreBtn.textContent = "Сохранено ✓";
        openLeaderboard();
      })
      .catch(() => {
        saveScoreBtn.disabled = false;
        saveScoreBtn.textContent = "Сохранить результат";
      });
  });

  // --- Keyboard nav for overlays: arrows move a highlight over the buttons,
  // Enter activates. The primary button (.btn.big) is highlighted by default.
  // A stack lets a modal (leaderboard/presave) sit on top of a menu and restore
  // it on close. Only active while an overlay is open — gameplay keys untouched. ---
  const kbStack = [];
  const kbTop = () => kbStack[kbStack.length - 1];
  function kbPaint(idx) {
    const m = kbTop();
    if (!m || !m.items.length) return;
    m.index = (idx + m.items.length) % m.items.length;
    m.items.forEach((el, i) => el.classList.toggle("kbd-active", i === m.index));
    m.items[m.index].focus({ preventScroll: true });
  }
  function kbItems(overlay) {
    return Array.from(overlay.querySelectorAll(".btn, .bl-row, .presave-close"))
      .filter((el) => el.offsetParent !== null && !el.disabled);
  }
  function kbOpen(overlay, push) {
    if (push) { const t = kbTop(); if (t) t.items.forEach((el) => el.classList.remove("kbd-active")); }
    else kbClear();
    const items = kbItems(overlay);
    if (!items.length) return;
    kbStack.push({ items, index: 0 });
    const big = items.findIndex((el) => el.classList.contains("big"));
    const row = items.findIndex((el) => el.classList.contains("bl-row"));
    kbPaint(big >= 0 ? big : row >= 0 ? row : 0);
  }
  function kbClose() {
    const m = kbStack.pop();
    if (m) m.items.forEach((el) => el.classList.remove("kbd-active"));
    const t = kbTop();
    if (t) kbPaint(t.index);
  }
  function kbClear() {
    kbStack.forEach((m) => m.items.forEach((el) => el.classList.remove("kbd-active")));
    kbStack.length = 0;
  }
  window.addEventListener("keydown", (e) => {
    const m = kbTop();
    if (!m) return;
    const ae = document.activeElement; // let a focused text field type normally
    if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) return;
    if (e.key === "Enter") { e.preventDefault(); m.items[m.index].click(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); kbPaint(m.index + 1); }
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); kbPaint(m.index - 1); }
  });

  // --- Game wiring ---
  const game = new Game("game");
  game.charIndex = getChar(localStorage);
  selectChar(game.charIndex);

  // --- Server config (Task 21/23): N points per revealed lyric line + the
  // world scroll-speed multiplier, tunable from /admin/settings. Fetch
  // failure falls back to sane defaults so the game is always playable. ---
  function applyConfig(cfg) {
    game.pointsPerLine = cfg.points_per_line;
    game.speedMult = cfg.speed_mult;
    game.lyricsCount = LYRICS.length;
  }
  fetch("/api/config")
    .then((r) => r.json())
    .then(applyConfig)
    .catch(() => applyConfig(CONFIG_FALLBACK));

  // Tracks g.caught (item catches only, not obstacle passes) so onScore can
  // tell a catch apart from a normal obstacle-passed point and play a blip.
  let lastCaught = 0;

  game.onStart = () => {
    emit("game_start", {});
    audio.startMusic();
    lastCaught = 0;
    renderLives(GAME.MAX_LIVES);
  };
  game.onScore = (s) => {
    scoreEl.textContent = String(s);
    const caughtNow = game.game.caught;
    if (caughtNow > lastCaught) sfxCatch();
    lastCaught = caughtNow;
  };
  game.onGameOver = (s) => {
    emit("game_over", { score: s });
    audio.sfxGameOver();
    finalScoreEl.textContent = String(s);
    updateBest(localStorage, s);
    renderBest();
    renderLives(0);
    // Arm the "save to leaderboard" control for this fresh result.
    lastGameScore = s;
    saveScoreBtn.disabled = false;
    saveScoreBtn.textContent = "Сохранить результат";
    nameInput.value = localStorage.getItem(NAME_KEY) || "";
    hud.classList.add("hidden");
    livesEl.classList.add("hidden");
    overEl.classList.remove("hidden");
    if (!isVariantA) fireCtaView(); // becomes visible only now, for variant B
    kbOpen(overEl);
  };
  // Non-fatal hit: game.js already paused + granted grace. Show the popup with
  // lives left, current score, Continue, and the presave CTA.
  game.onLifeLost = (livesLeft, score) => {
    sfxHit();
    renderLives(livesLeft);
    livesLeftEl.textContent = livesLeftText(livesLeft);
    lifeLostScoreEl.textContent = String(score);
    lifeLostEl.classList.remove("hidden");
    kbOpen(lifeLostEl);
  };
  // Lyric reveal (Task 23): game.js already paused gameplay before calling
  // this — just play the sting, pulse the score, and show the next line.
  game.onReveal = (i) => {
    audio.sfxReveal();
    scoreEl.classList.remove("pulse");
    void scoreEl.offsetWidth; // force reflow so the animation can retrigger
    scoreEl.classList.add("pulse");
    revealLineEl.textContent = LYRICS[i];
    revealPopup.classList.remove("hidden");
    kbOpen(revealPopup);
  };

  revealNextBtn.addEventListener("click", () => {
    kbClear();
    revealPopup.classList.add("hidden");
    game.resume();
  });

  continueBtn.addEventListener("click", () => {
    kbClear();
    lifeLostEl.classList.add("hidden");
    game.resume(); // grace window was already armed in game.js on the hit
  });

  function startPlay() {
    kbClear();
    startEl.classList.add("hidden");
    overEl.classList.add("hidden");
    lifeLostEl.classList.add("hidden");
    hud.classList.remove("hidden");
    livesEl.classList.remove("hidden");
    scoreEl.textContent = "0";
    game.start();
  }

  playBtn.addEventListener("click", startPlay);
  retryBtn.addEventListener("click", startPlay);

  // Game over -> back to the start screen (re-pick a character, etc.).
  toMenuBtn.addEventListener("click", () => {
    overEl.classList.add("hidden");
    leaderboardEl.classList.add("hidden");
    startEl.classList.remove("hidden");
    kbOpen(startEl);
  });

  muteBtn.addEventListener("click", () => {
    const muted = audio.toggleMute();
    muteBtn.textContent = muted ? "🔇" : "🔊";
  });

  kbOpen(startEl); // the start overlay is visible on load
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}
