// Page boot: wires the session/analytics (ab.js), the game controller
// (game.js), audio (audio.js), and the start/HUD/game-over overlays together.
import { readSession, markVisited, createEmitter, goPresaveUrl } from "./ab.js";
import { Game } from "./game.js";
import { createAudio } from "./audio.js";
import { getBest, updateBest, getChar, setChar } from "./prefs.js";
import { drawRunner, loadSprites } from "./sprites.js";
import { GAME } from "./config.js";
import { LYRICS } from "./lyrics.js";

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
  // Cover image is static in the template; only the presave link is dynamic.
  const ctaLink = ctaFrag.querySelector(".presave");
  ctaLink.href = goPresaveUrl(session.variant, session.sid, "button");
  // No client-side cta_click emit here: /go/presave (server) already logs
  // cta_click when the link is followed — emitting here would double-count.

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
