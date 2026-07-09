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
    this.lyrics = [];         // the actual line strings (set by boot.js) — drawn in
                              // the sky "cloud" on reveal
    this.revealed = 0;        // how many lines have been revealed so far

    // Lives (hearts): each obstacle hit costs one; the last hit is game over.
    this.lives = GAME.MAX_LIVES;
    this.invulnUntil = 0;     // this.t value until which collisions are ignored
                              // (pass-through grace after losing a life)
    this.growUntil = 0;       // this.t value until which the runner draws 2x-size
                              // (bonus-item power-up; see the special collectible)
    this.growStart = 0;       // this.t value when the grow began — drives the
                              // Mario-style grow ramp + blink (see _render)

    // Shell hooks — settable by Task 14. Kept simple and always callable.
    this.onStart = noop;
    this.onScore = noop;   // (score)
    this.onGameOver = noop; // (score)
    this.onReveal = noop;  // (lyricIndex) — fired when a new line is revealed; game is already paused
    this.onLifeLost = noop; // (livesLeft, score) — fired on a non-fatal hit; game is already paused
    this.onLifeGain = noop; // (lives) — fired when the Плов bonus item restores a life
    this.onShrink = noop;   // () — fired when a big (Плов) runner absorbs a hit instead
                            // of losing a life; shell plays the hit sound
    this.onGain = noop;     // (amount, special) — a score gain (catch/pass); shell plays a blip
    this.onTime = noop;     // (seconds) — in-game play time; only advances while running

    // Floating "+N" reward popups above the runner: {text, x, y, t0, color}.
    this.popups = [];
    // Active lyric "cloud" in the sky: {text, t0} or null. Non-blocking — the game
    // keeps running while it shows (REVEAL_SHOW_TIME) then fades.
    this.reveal = null;

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
    this.growUntil = 0;
    this.growStart = 0;
    this.t = 0;
    this.cam.x = 0;
    this.popups.length = 0;
    this.reveal = null;
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

  // Manual pause (pause button). Freezes gameplay + the play-time clock (t/cam
  // only advance while running); the RAF keeps rendering the frozen scene.
  pause() {
    if (this.game.state === "running") this.game.state = "paused";
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
    const fit = Math.min(cssH / GAME.WORLD_H, cssW / GAME.MIN_VIEW_W); // logical -> css
    // Snap logical->device to an INTEGER factor: every logical pixel then maps to
    // a whole block of device pixels. A fractional factor is what made the moving
    // pixel art shimmer (fillRect edges re-alias every frame); an integer factor
    // keeps it crisp AND stable with no buffer/blur trickery. imageSmoothing is
    // left on so the high-res image sprites downscale cleanly — fillRect pixel
    // art ignores it, so it stays sharp.
    const deviceScale = Math.max(1, Math.round(dpr * fit));
    const scale = deviceScale / dpr;
    this.scale = scale;
    this.worldW = cssW / scale; // visible world width
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round(cssH * dpr);
    // On mobile the scaled world (WORLD_H * scale) is shorter than the canvas
    // — anchor it to the bottom (world y=WORLD_H -> canvas bottom) so the
    // ground/sea/sand band stays put instead of floating mid-screen. On
    // desktop this offset is 0 (world already fills the height).
    this.yOffset = cssH - GAME.WORLD_H * scale; // CSS px
    // The y-offset is rounded to a whole device pixel so integer logical coords
    // stay integer in device space (no sub-pixel drift -> no shimmer).
    this.ctx.setTransform(deviceScale, 0, 0, deviceScale, 0, Math.round(dpr * this.yOffset));
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = "high";
  }

  // One discrete jump per input event while running. Single tap = one jump,
  // double tap = double jump — that comes for free from physics.jump()'s max-2.
  handleJump() {
    if (this.game.state !== "running") return;
    // While grown (Плов power-up) jump GROW_JUMP_MULT× higher. Peak height goes
    // with velocity², so the velocity boost is sqrt of the height multiplier.
    const grown = this.t < this.growUntil;
    const vMult = grown ? Math.sqrt(GAME.GROW_JUMP_MULT) : 1;
    jump(this.game.runner, vMult);
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
    const { over, scoreDelta, grew, obstacleDelta, caughtPoints } =
      stepGame(this.game, dt, this.worldW, invulnerable);
    // Bonus item (Плов) caught: (re)start the 2x-size window (game-time `t`, so
    // it freezes on pause) and restore one life, capped at MAX_LIVES.
    if (grew) {
      this.growStart = this.t;
      this.growUntil = this.t + GAME.GROW_TIME;
      if (this.lives < GAME.MAX_LIVES) {
        this.lives += 1;
        this.onLifeGain(this.lives);
      }
    }

    // Reward feedback: a floating "+N" above the runner + a blip (onGain), for
    // both catching an item and clearing an obstacle.
    if (caughtPoints > 0) {
      this._addPopup("+" + caughtPoints, grew ? PALETTE.sun : PALETTE.arcade);
      this.onGain(caughtPoints, grew);
    }
    if (obstacleDelta > 0) {
      this._addPopup("+" + obstacleDelta, PALETTE.foam);
      this.onGain(obstacleDelta, false);
    }

    // Only advance time/camera/reveal-checks while actually running — this is
    // what makes a lyric-reveal pause read as a genuinely frozen scene rather
    // than just obstacles halting while everything else keeps moving.
    if (this.game.state === "running") {
      this.t += dt;
      this.cam.x += this.game.obs.speed * dt;
      this.onTime(this.t);

      // Reveal the next lyric line as a non-blocking "cloud" in the sky — the game
      // keeps running. The final line is the exception: it pauses for the
      // whole-song celebration (the shell shows it). nextRevealIndex is score-driven.
      const idx = nextRevealIndex(this.game.score, this.pointsPerLine, this.revealed, this.lyricsCount);
      if (idx !== null) {
        this.revealed++;
        if (this.revealed >= this.lyricsCount) {
          this.game.state = "paused"; // final line: celebrate the whole song
        } else {
          this.reveal = { text: this.lyrics[idx] || "", t0: this.t };
        }
        this.onReveal(idx);
      }
    }

    if (scoreDelta) this.onScore(this.game.score);

    // A hit while BIG (Плов power-up) costs no life: the runner just shrinks back
    // to normal and keeps running (Mario-style). Still plays the hit sound + grants
    // the usual pass-through grace so it doesn't instantly re-hit. Otherwise a hit
    // costs a life: with lives left, pause + grace + "life lost" popup; out of
    // lives, the game-over flow.
    if (over) {
      if (this.t < this.growUntil) {
        this.growUntil = 0;
        this.growStart = 0;
        this.invulnUntil = this.t + GAME.INVULN_TIME;
        this.game.state = "running"; // stepGame set it to "over"; keep playing
        this.onShrink();
      } else {
        this.lives -= 1;
        if (this.lives > 0) {
          this.game.state = "paused";
          this.invulnUntil = this.t + GAME.INVULN_TIME;
          this.onLifeLost(this.lives, this.game.score);
        } else {
          this.onGameOver(this.game.score);
        }
      }
    }

    this._render();
    this.raf = requestAnimationFrame(this._frame);
  }

  // Queue a floating "+N" above the runner's current head position.
  _addPopup(text, color) {
    this.popups.push({
      text,
      x: GAME.RUNNER_X + GAME.RUNNER_W / 2,
      y: this.game.runner.y - GAME.RUNNER_H * GAME.BASE_SCALE - 8,
      t0: this.t,
      color,
    });
    if (this.popups.length > 12) this.popups.shift();
  }

  // Wrap `text` into lines no wider than maxW (in the current ctx font). Greedy
  // word-wrap; a single over-long word is left on its own line.
  _wrapText(ctx, text, maxW) {
    const words = String(text).split(" ");
    const lines = [];
    let cur = "";
    for (const w of words) {
      const test = cur ? cur + " " + w : w;
      if (cur && ctx.measureText(test).width > maxW) { lines.push(cur); cur = w; }
      else cur = test;
    }
    if (cur) lines.push(cur);
    return lines;
  }

  _roundRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // Lyric "cloud": a soft cream bubble holding the revealed line, with a small
  // caption above it. Non-blocking; shows for GAME.REVEAL_SHOW_TIME then fades.
  // Drawn in SCREEN space (device px) at a fixed spot just below the HUD/timer so
  // it never collides with the timer regardless of the device's world→screen
  // mapping. Drawn before the runner + "+N" popups so those always sit on top.
  _drawRevealCloud(ctx) {
    const r = this.reveal;
    if (!r || !r.text) return;
    const age = this.t - r.t0;
    const LIFE = GAME.REVEAL_SHOW_TIME;
    if (age < 0 || age >= LIFE) { this.reveal = null; return; }
    const FADE = 0.9;
    const alpha = age > LIFE - FADE ? Math.max(0, (LIFE - age) / FADE) : 1;

    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const W = this.canvas.width; // device px
    // Size the cloud in the GAME's scale (device px per world px) so it reads the
    // same relative to the runner/road — NOT raw CSS px, which renders tiny on a
    // big low-dpr desktop canvas. But CAP that scale: on desktop the world scale
    // is high (~3 at 1080p) which ballooned the cloud; clamping keeps it modest
    // there while leaving phones (scale ~1.3) untouched. Its vertical position is
    // anchored to the CSS-positioned HUD (dpr px from the top), not the game scale.
    const cs = Math.min(this.scale || 1, 1.5);
    const u = (v) => Math.round(v * cs * dpr); // world px (game-scaled, capped) -> device px
    const cssPx = (v) => Math.round(v * dpr);  // CSS px -> device px
    const label = "Открыта новая строка песни:";
    const labelFont = `${u(12)}px "ProgressPixel", monospace`;
    const lineFont = `700 ${u(17)}px "ProgressPixelPab", monospace`;

    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0); // screen/device space
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const padX = u(15);
    ctx.font = lineFont;
    // Lyrics carry a fixed "\n" break (always exactly two display lines);
    // word-wrap stays as a fallback for any text without one.
    const maxTextW = Math.min(W * 0.92, u(310)) - padX * 2;
    const lines = r.text.includes("\n")
      ? r.text.split("\n")
      : this._wrapText(ctx, r.text, maxTextW);
    const lineH = u(22);
    const labelH = u(18);
    let boxW = padX * 2;
    for (const ln of lines) boxW = Math.max(boxW, ctx.measureText(ln).width + padX * 2);
    ctx.font = labelFont;
    boxW = Math.max(boxW, ctx.measureText(label).width + padX * 2);
    const boxH = u(9) + labelH + lines.length * lineH + u(9);
    const cx = W / 2;
    const x = Math.round(cx - boxW / 2);
    const y = cssPx(128); // just under the HUD/timer band (CSS-positioned)

    ctx.globalAlpha = alpha;
    this._roundRectPath(ctx, x, y, boxW, boxH, u(11));
    ctx.fillStyle = "rgba(255, 244, 226, 0.94)"; // foam-cream cloud
    ctx.fill();
    ctx.lineWidth = u(2);
    ctx.strokeStyle = "rgba(109, 46, 139, 0.55)"; // grape edge
    ctx.stroke();
    // Caption (smaller, muted).
    ctx.fillStyle = "rgba(42, 21, 51, 0.68)";
    ctx.font = labelFont;
    ctx.fillText(label, cx, y + u(9) + labelH / 2);
    // Lyric line(s).
    ctx.fillStyle = PALETTE.ink;
    ctx.font = lineFont;
    const textTop = y + u(9) + labelH;
    lines.forEach((ln, i) => ctx.fillText(ln, cx, textTop + lineH / 2 + i * lineH));
    ctx.restore();
  }

  // Draw + age the reward popups: rise ~26px and fade over POPUP_LIFE seconds.
  _drawPopups(ctx) {
    const LIFE = 0.9;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = '700 15px "ProgressPixelPab", monospace';
    for (let i = this.popups.length - 1; i >= 0; i--) {
      const p = this.popups[i];
      const age = this.t - p.t0;
      if (age >= LIFE || age < 0) { this.popups.splice(i, 1); continue; }
      const k = age / LIFE;
      ctx.globalAlpha = 1 - k * k;
      ctx.fillStyle = p.color;
      const y = p.y - k * 26;
      ctx.fillText(p.text, p.x, y);
    }
    ctx.restore();
  }

  _render() {
    const ctx = this.ctx;
    if (!ctx) return;
    // Paint the strip above the world (extra sky on tall phones) with the sky's
    // top colour first, in device space; drawBackground's gradient covers the
    // world area over it.
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = PALETTE.night;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.restore();
    // viewTop = world-y at the canvas top (negative on mobile) so drawBackground
    // stretches the sky across the full visible height.
    const viewTop = this.scale ? -this.yOffset / this.scale : 0;
    drawBackground(ctx, this.cam, this.worldW, viewTop);
    for (const o of this.game.obs.obstacles) drawObstacle(ctx, o);
    for (const item of this.game.col.items) drawCollectible(ctx, item);
    // Lyric "cloud" in the sky — drawn BEFORE the runner + "+N" popups so those
    // always sit on top of it (per the design).
    this._drawRevealCloud(ctx);
    // Runner draw size + blink. Two things can make the runner blink: post-hit
    // invulnerability grace, and the Mario-style grow after eating Плов.
    const invulnerable = this.t < this.invulnUntil;
    const grown = this.t < this.growUntil;
    const growAge = this.t - this.growStart;
    // Grow ramp: scale eases BASE_SCALE -> GROW_SCALE over GROW_ANIM_TIME so the
    // runner passes through an intermediate size instead of popping to full size.
    let grow = GAME.BASE_SCALE;
    if (grown) {
      const k = Math.min(1, growAge / GAME.GROW_ANIM_TIME);
      grow = GAME.BASE_SCALE + (GAME.GROW_SCALE - GAME.BASE_SCALE) * k;
    }
    // Blink for GROW_BLINK_TIME after eating Плов (covers the grow second + one
    // more), on top of the post-hit invuln blink.
    const growBlinking = grown && growAge < GAME.GROW_BLINK_TIME;
    const blinking = invulnerable || growBlinking;
    if (!blinking || Math.floor(this.t * 10) % 2 === 0) {
      drawRunner(ctx, this.game.runner, this.t, this.charIndex, grow);
    }
    this._drawPopups(ctx);
  }
}
