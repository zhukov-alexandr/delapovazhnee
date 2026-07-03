// DOM glue for the runner game: canvas sizing, RAF loop, input, and a small
// Game controller the page shell (Task 14) wires start/restart + analytics into.
//
// IMPORTANT: nothing here touches the DOM or requestAnimationFrame at module
// top level — every browser API is reached only from inside a method, so the
// module can be imported (e.g. under Node for a smoke import) without side effects.
import { GAME } from "./config.js";
import { jump } from "./physics.js";
import { createGame, startGame, stepGame, nextRevealIndex } from "./gamestate.js";
import { drawBackground, drawRunner, drawObstacle, drawCollectible, PALETTE } from "./sprites.js";

// A no-op default so hooks are always callable before the shell sets real ones.
const noop = () => {};

export class Game {
  // canvas: an HTMLCanvasElement (or its id string, resolved in start()).
  constructor(canvas) {
    this.canvasRef = canvas;
    this.game = createGame(); // { runner, obs, state, score }

    // Cosmetic-only character variant (0-3), passed through to drawRunner.
    // Settable by the shell (boot.js) before start(); no effect on physics.
    this.charIndex = 0;

    // Server-tunable config (Task 21/23), set by boot.js from GET /api/config.
    // Sane fallbacks here keep the game playable before that fetch resolves.
    this.pointsPerLine = 5;   // N: score points per revealed lyric line
    this.speedMult = 1;       // scales RUN_SPEED/MAX_SPEED (obstacles.js)
    this.lyricsCount = 0;     // total lines available to reveal (LYRICS.length)
    this.revealed = 0;        // how many lines have been revealed so far

    // Lives (hearts): each obstacle hit costs one; the last hit is game over.
    this.lives = GAME.MAX_LIVES;
    this.invulnUntil = 0;     // this.t value until which collisions are ignored
                              // (pass-through grace after losing a life)

    // Shell hooks — settable by Task 14. Kept simple and always callable.
    this.onStart = noop;
    this.onScore = noop;   // (score)
    this.onGameOver = noop; // (score)
    this.onReveal = noop;  // (lyricIndex) — fired when a new line is revealed; game is already paused
    this.onLifeLost = noop; // (livesLeft, score) — fired on a non-fatal hit; game is already paused

    // Runtime handles created lazily in start(); null until then.
    this.canvas = null;
    this.ctx = null;
    this.worldW = 640; // visible world width in logical px; recomputed in resize()
    this.scale = 1;    // logical->css scale; recomputed in resize()
    this.yOffset = 0;  // CSS px the world is pushed down to anchor its bottom to the
                        // canvas bottom on mobile (see resize()); 0 on desktop
    this.cam = { x: 0 }; // parallax camera; advances with elapsed time
    this.t = 0;          // seconds elapsed, drives run-bob + parallax
    this.raf = 0;
    this.last = 0;
    this.running = false; // whether the RAF loop is active

    // Offscreen 1:1-logical render buffer (created in _resize): the scene is
    // drawn here at crisp integer pixels and upscaled to the device canvas in a
    // single blit, which kills the moving-pixel-art shimmer.
    this.buffer = null;
    this.bufferCtx = null;
    this.bufW = 0;
    this.bufH = 0;
    this.viewTop = 0;
    this.skyShift = 0;

    // Bound listeners so we can add/remove the exact same references.
    this._onResize = this._resize.bind(this);
    this._onKeyDown = this.__keydown.bind(this);
    this._onMouseDown = this.__mousedown.bind(this);
    this._onTouchStart = this.__touchstart.bind(this);
    this._frame = this._frame.bind(this);
  }

  // Boot the loop: resolve the canvas, wire input + resize, size the backing
  // store, start the game state, and kick off requestAnimationFrame.
  start() {
    if (!this.canvas) this._mount();
    startGame(this.game, this.speedMult);
    this.revealed = 0;
    this.lives = GAME.MAX_LIVES;
    this.invulnUntil = 0;
    this.t = 0;
    this.cam.x = 0;
    this.onStart();
    this._resize();
    if (!this.running) {
      this.running = true;
      this.last = performance.now();
      this.raf = requestAnimationFrame(this._frame);
    }
  }

  // Restart from a fresh state (used by the shell's replay control).
  reset() {
    this.start();
  }

  // Unpause after a lyric-reveal popup is dismissed. Resets `last` so the
  // next frame's dt is small (otherwise the paused wall-clock gap would be
  // read as one huge dt and could tunnel the runner through an obstacle).
  resume() {
    this.game.state = "running";
    this.last = performance.now();
  }

  // Resolve the canvas element + 2D context and attach listeners. Idempotent.
  _mount() {
    const el =
      typeof this.canvasRef === "string"
        ? document.getElementById(this.canvasRef)
        : this.canvasRef;
    if (!el) throw new Error("Game: canvas element not found");
    this.canvas = el;
    this.ctx = el.getContext("2d");
    // Let the browser handle taps without emulating 300ms click / gestures.
    this.canvas.style.touchAction = "manipulation";

    window.addEventListener("resize", this._onResize);
    window.addEventListener("orientationchange", this._onResize);
    window.addEventListener("keydown", this._onKeyDown);
    this.canvas.addEventListener("mousedown", this._onMouseDown);
    this.canvas.addEventListener("touchstart", this._onTouchStart, { passive: false });
  }

  // Fixed logical height (WORLD_H); CSS fills the viewport; backing store is
  // scaled by devicePixelRatio for crisp pixels. worldW = visible world width.
  //
  // Camera fit (Task 24): height-fit alone over-zooms on tall/narrow phones —
  // the visible world width shrinks along with the height scale, so the fixed
  // runner (GAME.RUNNER_X=90) ends up near the horizontal center with almost
  // no track ahead to react to. Capping the scale so the visible width never
  // drops below GAME.MIN_VIEW_W fixes that: desktop/landscape (cssH/WORLD_H is
  // the smaller term) renders exactly as before; narrow/tall mobile picks the
  // smaller cssW/MIN_VIEW_W term instead, zooming out so everything is smaller
  // and the runner sits well left of center with real track ahead. This is a
  // camera-only change — RUNNER_X and all obstacle/physics logic are untouched.
  _resize() {
    if (!this.canvas || !this.ctx) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const cssH = this.canvas.clientHeight;
    const cssW = this.canvas.clientWidth;
    if (!cssH || !cssW) return; // not laid out yet
    const scale = Math.min(cssH / GAME.WORLD_H, cssW / GAME.MIN_VIEW_W); // logical -> css
    this.scale = scale;
    this.worldW = cssW / scale; // visible world width
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round(cssH * dpr);
    // On mobile the scaled world (WORLD_H * scale) is shorter than the canvas
    // — anchor it to the bottom (world y=WORLD_H -> canvas bottom) so the
    // ground/sea/sand band stays put instead of floating mid-screen. On
    // desktop this offset is 0 (world already fills the height).
    this.yOffset = cssH - GAME.WORLD_H * scale; // CSS px
    this.viewTop = scale ? -this.yOffset / scale : 0; // world-y at the canvas top

    // (Re)build the offscreen buffer at logical resolution. Everything is drawn
    // into it at integer logical pixels (px() rounds to 1px); a single uniform
    // upscale to the device canvas then avoids the per-sprite sub-pixel shimmer
    // you get drawing moving pixel art directly through the fractional dpr*scale
    // transform (fillRect edges re-alias every frame).
    this.bufW = Math.max(1, Math.ceil(this.worldW));
    this.bufH = Math.max(1, Math.ceil(GAME.WORLD_H - this.viewTop));
    this.skyShift = Math.round(this.viewTop); // integer sky offset in the buffer
    if (!this.buffer) this.buffer = document.createElement("canvas");
    this.buffer.width = this.bufW;
    this.buffer.height = this.bufH;
    this.bufferCtx = this.buffer.getContext("2d");
    this.bufferCtx.imageSmoothingEnabled = false; // scene is crisp in the buffer
    // The buffer -> device upscale is SMOOTH (bilinear): a nearest upscale by a
    // fractional factor makes sprite edges wobble ±1 device px as they scroll
    // (residual shimmer); smoothing the single uniform upscale removes it.
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = "high";
  }

  // One discrete jump per input event while running. Single tap = one jump,
  // double tap = double jump — that comes for free from physics.jump()'s max-2.
  handleJump() {
    if (this.game.state === "running") jump(this.game.runner);
  }

  __keydown(e) {
    if (e.code === "Space" || e.code === "ArrowUp") {
      e.preventDefault(); // stop the page from scrolling on Space/ArrowUp
      this.handleJump();
    }
  }

  __mousedown() {
    this.handleJump();
  }

  __touchstart(e) {
    e.preventDefault(); // suppress synthetic mouse events + scrolling
    this.handleJump();
  }

  // RAF loop: advance state by a clamped dt, fire hooks, render.
  _frame(now) {
    const dt = Math.min((now - this.last) / 1000, 1 / 30); // clamp: no tunneling on tab-switch
    this.last = now;

    const invulnerable = this.t < this.invulnUntil;
    const { over, scoreDelta } = stepGame(this.game, dt, this.worldW, invulnerable);

    // Only advance time/camera/reveal-checks while actually running — this is
    // what makes a lyric-reveal pause read as a genuinely frozen scene rather
    // than just obstacles halting while everything else keeps moving.
    if (this.game.state === "running") {
      this.t += dt;
      this.cam.x += this.game.obs.speed * dt;

      const idx = nextRevealIndex(this.game.score, this.pointsPerLine, this.revealed, this.lyricsCount);
      if (idx !== null) {
        this.game.state = "paused";
        this.onReveal(idx);
        this.revealed++;
      }
    }

    if (scoreDelta) this.onScore(this.game.score);

    // A hit costs a life. With lives left: pause + grant pass-through grace so
    // resuming doesn't re-hit the same obstacle, and let the shell show the
    // "life lost" popup. Out of lives: the existing game-over flow.
    if (over) {
      this.lives -= 1;
      if (this.lives > 0) {
        this.game.state = "paused";
        this.invulnUntil = this.t + GAME.INVULN_TIME;
        this.onLifeLost(this.lives, this.game.score);
      } else {
        this.onGameOver(this.game.score);
      }
    }

    this._render();
    this.raf = requestAnimationFrame(this._frame);
  }

  _render() {
    const bctx = this.bufferCtx;
    const ctx = this.ctx;
    if (!bctx || !ctx) return;

    // 1) Draw the whole scene into the logical-resolution buffer. Content at
    // logical y lands at buffer y = logical_y - skyShift, so the sky top sits at
    // the buffer's top edge (mobile has extra sky above the world). The night
    // fill first covers any strip the background doesn't reach.
    bctx.setTransform(1, 0, 0, 1, 0, 0);
    bctx.fillStyle = PALETTE.night;
    bctx.fillRect(0, 0, this.bufW, this.bufH);
    bctx.setTransform(1, 0, 0, 1, 0, -this.skyShift);
    drawBackground(bctx, this.cam, this.worldW, this.viewTop);
    for (const o of this.game.obs.obstacles) drawObstacle(bctx, o);
    for (const item of this.game.col.items) drawCollectible(bctx, item);
    // Blink the runner while invulnerable (post-life-loss grace) as feedback.
    const invulnerable = this.t < this.invulnUntil;
    if (!invulnerable || Math.floor(this.t * 10) % 2 === 0) {
      drawRunner(bctx, this.game.runner, this.t, this.charIndex);
    }

    // 2) Upscale the crisp buffer to the device canvas in one smooth (bilinear)
    // blit — temporally stable, so moving pixels no longer shimmer.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.drawImage(this.buffer, 0, 0, this.bufW, this.bufH, 0, 0, this.canvas.width, this.canvas.height);
  }
}
