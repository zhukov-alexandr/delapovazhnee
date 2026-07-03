// Page boot: wires the session/analytics (ab.js), the game controller
// (game.js), audio (audio.js), and the start/HUD/game-over overlays together.
import { readSession, markVisited, createEmitter } from "./ab.js";
import { Game } from "./game.js";
import { createAudio } from "./audio.js";
import { getBest, updateBest, getChar, setChar } from "./prefs.js";
import { drawRunner, loadSprites } from "./sprites.js";
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

// Placeholder tile art (before real PNGs exist): render the same procedural
// runner sprites.drawRunner() draws in-game, scaled/centered into the tile's
// small canvas. A fake "runner" (just {y, onGround}) is enough since
// drawRunner only reads those two fields.
function drawRunnerPreview(ctx, charIndex, w, h) {
  ctx.clearRect(0, 0, w, h);
  ctx.save();
  // drawRunner always paints a GAME.RUNNER_W x GAME.RUNNER_H box with its
  // top-left at (GAME.RUNNER_X, runner.y - RUNNER_H); undo that fixed
  // position and re-center+scale the box into this small tile canvas.
  const scale = (Math.min(w, h) * 0.85) / Math.max(GAME.RUNNER_W, GAME.RUNNER_H);
  const boxLeft = GAME.RUNNER_X;
  const boxTop = 0; // runner.y === RUNNER_H below puts the box top at y=0
  ctx.translate(
    w / 2 - scale * (boxLeft + GAME.RUNNER_W / 2),
    h / 2 - scale * (boxTop + GAME.RUNNER_H / 2)
  );
  ctx.scale(scale, scale);
  drawRunner(ctx, { y: GAME.RUNNER_H, onGround: true }, 0, charIndex);
  ctx.restore();
}

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

function boot() {
  // Drop-in PNGs auto-swap on reload; missing files silently keep procedural art.
  loadSprites({
    char_0: "/static/sprites/characters/char1.png",
    char_1: "/static/sprites/characters/char2.png",
    char_2: "/static/sprites/characters/char3.png",
    char_3: "/static/sprites/characters/char4.png",
    item_0: "/static/sprites/items/item1.png",
    item_1: "/static/sprites/items/item2.png",
    item_2: "/static/sprites/items/item3.png",
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
    const canvas = tile.querySelector("canvas");
    if (canvas) {
      const tileCtx = canvas.getContext("2d");
      tileCtx.imageSmoothingEnabled = false;
      // Placeholder art before PNGs exist: draw the same procedural runner
      // used in-game, centered in the tile.
      drawRunnerPreview(tileCtx, idx, canvas.width, canvas.height);
    }
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

  // Only these three resolve correctly through band.link's save-presave gateway
  // AND honor our redirectUrl. Through that gateway Spotify/Apple silently fall
  // back to a Yandex login, so they are built directly below (verified against
  // the original dnkmusic.ru page).
  const GATEWAY_SERVICES = new Set(["yandex", "vkmusic", "mts"]);

  // Opens the correct presave flow for one service in a popup. No "noopener":
  // the /presave/return popup needs window.opener to postMessage back here.
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
      emit("streaming_click", { service: svc.id });
      openPresave(svc.id);
    });
    presaveServicesEl.appendChild(li);
  }

  function openPresaveModal() {
    for (const id of readPresaved(localStorage)) markRowSaved(id);
    presaveModal.classList.remove("hidden");
  }

  presaveClose.addEventListener("click", () => {
    presaveModal.classList.add("hidden");
  });

  const PRESAVE_IDS = new Set(PRESAVE.SERVICES.map((s) => s.id));
  window.addEventListener("message", (e) => {
    const data = e.data;
    if (!data || data.dp !== "presave_done" || !PRESAVE_IDS.has(data.service)) return;
    addPresaved(localStorage, data.service);
    markRowSaved(data.service);
    // Server already logged presave_done for this return — no emit here.
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
    hud.classList.add("hidden");
    overEl.classList.remove("hidden");
    if (!isVariantA) fireCtaView(); // becomes visible only now, for variant B
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
  };

  revealNextBtn.addEventListener("click", () => {
    revealPopup.classList.add("hidden");
    game.resume();
  });

  function startPlay() {
    startEl.classList.add("hidden");
    overEl.classList.add("hidden");
    hud.classList.remove("hidden");
    scoreEl.textContent = "0";
    game.start();
  }

  playBtn.addEventListener("click", startPlay);
  retryBtn.addEventListener("click", startPlay);

  muteBtn.addEventListener("click", () => {
    const muted = audio.toggleMute();
    muteBtn.textContent = muted ? "🔇" : "🔊";
  });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}
