// Procedural sunset-pixel art + parallax background renderer.
// No game-loop/input/DOM-query logic here — pure rendering from GAME + shapes.
// Swap point: each draw* checks images[name] first; when a real PNG is loaded
// there, it is blitted via drawImage and the primitive fallback is skipped.
import { GAME } from "./config.js";

// Summer Sunset Pixel (PS1/Sega) — authoritative palette, reused across game + admin.
export const PALETTE = {
  night: "#241539",
  grape: "#6D2E8B",
  flare: "#FF5D73",
  sun: "#FFD35C",
  sand: "#F2C078",
  foam: "#FFF4E2",
  arcade: "#2FE6D6",
  ink: "#2A1533",
};

// name -> HTMLImageElement. Empty until loadSprites() populates it.
export const images = {};

// Populate images from a manifest: { name: url, ... }. Returns a Promise that
// resolves once every image has attempted to load (errors are swallowed so a
// missing PNG just leaves the procedural fallback in place).
export function loadSprites(manifest) {
  const entries = Object.entries(manifest || {});
  return Promise.all(
    entries.map(([name, src]) =>
      new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          images[name] = img;
          resolve();
        };
        img.onerror = () => resolve();
        img.src = src;
      })
    )
  );
}

// Sea sits just above the sand; sun disc sits just above the sea line.
const SEA_Y = GAME.GROUND_Y + 4;
const SEA_H = 22;
const SAND_H = GAME.WORLD_H - (SEA_Y + SEA_H);

function px(n) {
  return Math.round(n);
}

function drawDitherBand(ctx, x, y, w, h, color, alpha) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  // Ordered dither: alternate-column pixel stipple, 2px chunky pixels.
  for (let py = 0; py < h; py += 2) {
    for (let pxi = 0; pxi < w; pxi += 2) {
      if (((pxi >> 1) + (py >> 1)) % 2 === 0) {
        ctx.fillRect(px(x + pxi), px(y + py), 2, 2);
      }
    }
  }
  ctx.restore();
}

// Sky fills the FULL visible height: from viewTop (world-y at the canvas top —
// negative & far up on tall/portrait mobile) down to the horizon (sea line), so
// there's a real sunset gradient instead of a flat dead band above a short world.
function drawSky(ctx, w, viewTop, horizon) {
  const h = horizon - viewTop;
  if (images.sky) {
    ctx.drawImage(images.sky, 0, px(viewTop), w, px(h));
    return;
  }
  const grad = ctx.createLinearGradient(0, viewTop, 0, horizon);
  grad.addColorStop(0, PALETTE.night);
  grad.addColorStop(0.5, PALETTE.grape);
  grad.addColorStop(0.78, PALETTE.flare);
  grad.addColorStop(1, PALETTE.sun);
  ctx.fillStyle = grad;
  ctx.fillRect(0, px(viewTop), w, px(h) + 2);
  // Ordered-dither band just above the horizon for the PS1 sunset feel.
  drawDitherBand(ctx, 0, px(horizon - h * 0.16), w, px(h * 0.12), PALETTE.flare, 0.22);
}

function drawSun(ctx, cam, w) {
  const cx = px(w * 0.68 - cam.x * 0.08);
  const cy = px(SEA_Y - 78);
  const r = 66;
  if (images.sun) {
    ctx.drawImage(images.sun, cx - r, cy - r, r * 2, r * 2);
    return;
  }
  ctx.save();
  ctx.fillStyle = PALETTE.sun;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  // Ordered-dither horizontal stripes across the lower half of the disc —
  // the "signature" dithered sunset look.
  ctx.save();
  ctx.fillStyle = PALETTE.flare;
  for (let dy = 0; dy < r; dy += 4) {
    const rowY = cy + dy;
    const half = Math.sqrt(Math.max(0, r * r - dy * dy));
    const rowW = px(half * 2);
    ctx.globalAlpha = 0.35;
    ctx.fillRect(px(cx - half), px(rowY), rowW, 2);
  }
  ctx.restore();
}

function drawSea(ctx, cam, w) {
  if (images.sea) {
    ctx.drawImage(images.sea, 0, SEA_Y, w, SEA_H);
    return;
  }
  const offset = ((cam.x * 0.4) % 40 + 40) % 40;
  ctx.fillStyle = PALETTE.grape;
  ctx.fillRect(0, px(SEA_Y), w, SEA_H);
  // Parallax "wave" ticks scrolling with a medium factor of cam.x.
  ctx.fillStyle = PALETTE.foam;
  for (let x = -offset; x < w; x += 40) {
    ctx.fillRect(px(x), px(SEA_Y + 6), 16, 2);
  }
}

function drawSand(ctx, cam, w, h) {
  if (images.sand) {
    ctx.drawImage(images.sand, 0, SEA_Y + SEA_H, w, SAND_H);
    return;
  }
  const y = SEA_Y + SEA_H;
  ctx.fillStyle = PALETTE.sand;
  ctx.fillRect(0, px(y), w, px(h - y));
  // Fastest parallax layer: sand speckle scrolls at full cam.x rate.
  const offset = ((cam.x % 24) + 24) % 24;
  ctx.fillStyle = PALETTE.ink;
  ctx.save();
  ctx.globalAlpha = 0.15;
  for (let x = -offset; x < w; x += 24) {
    ctx.fillRect(px(x), px(y + 10), 4, 4);
  }
  ctx.restore();
}

// Layer order: sky gradient -> sun -> sea band -> sand (each with its own
// parallax factor driven by cam.x: sky+sun slowest, sea medium, sand fastest).
export function drawBackground(ctx, cam, worldW, viewTop = 0) {
  ctx.imageSmoothingEnabled = false;
  const h = GAME.WORLD_H;
  drawSky(ctx, worldW, viewTop, SEA_Y);
  drawSun(ctx, cam, worldW);
  drawSea(ctx, cam, worldW);
  drawSand(ctx, cam, worldW, h);
}

// One procedural look per character index: torso/head accent color + a small
// silhouette tweak so the 4 variants are tellable apart at a glance.
const CHAR_VARIANTS = [
  { torso: PALETTE.flare, head: PALETTE.sand, trim: PALETTE.sun },   // 0: default sunset runner
  { torso: PALETTE.arcade, head: PALETTE.foam, trim: PALETTE.grape }, // 1: arcade teal
  { torso: PALETTE.grape, head: PALETTE.sun, trim: PALETTE.flare },  // 2: grape/sun
  { torso: PALETTE.sun, head: PALETTE.ink, trim: PALETTE.arcade },   // 3: sun/ink
];

// Procedural pixel runner with a slight run bob driven by t. charIndex (0-3)
// selects one of 4 visually distinct palette variants.
export function drawRunner(ctx, runner, t, charIndex = 0) {
  ctx.imageSmoothingEnabled = false;
  const w = GAME.RUNNER_W;
  const h = GAME.RUNNER_H;
  const x = GAME.RUNNER_X;
  const y = runner.y - h;
  const bob = runner.onGround ? Math.round(Math.sin(t * 12) * 2) : 0;

  if (images["char_" + charIndex]) {
    ctx.drawImage(images["char_" + charIndex], px(x), px(y + bob), w, h);
    return;
  }

  const variant = CHAR_VARIANTS[charIndex] || CHAR_VARIANTS[0];

  ctx.save();
  ctx.fillStyle = PALETTE.ink;
  // legs
  ctx.fillRect(px(x + 6), px(y + h - 12 + bob), 8, 12);
  ctx.fillRect(px(x + w - 14), px(y + h - 12 + bob), 8, 12);
  // torso
  ctx.fillStyle = variant.torso;
  ctx.fillRect(px(x + 4), px(y + h * 0.35 + bob), w - 8, h * 0.4);
  // trim stripe across the torso — extra silhouette cue per variant
  ctx.fillStyle = variant.trim;
  ctx.fillRect(px(x + 4), px(y + h * 0.5 + bob), w - 8, 4);
  // head
  ctx.fillStyle = variant.head;
  ctx.fillRect(px(x + 8), px(y + bob), w - 16, h * 0.3);
  ctx.restore();
}

function drawSingleObstacle(ctx, o) {
  if (images.single) {
    ctx.drawImage(images.single, px(o.x), px(o.y), o.w, o.h);
    return;
  }
  ctx.save();
  // Mat
  ctx.fillStyle = PALETTE.arcade;
  ctx.fillRect(px(o.x), px(o.y + o.h - 8), o.w, 8);
  // Sunbather body lying on the mat
  ctx.fillStyle = PALETTE.sand;
  ctx.fillRect(px(o.x + o.w * 0.15), px(o.y + o.h - 18), o.w * 0.7, 10);
  ctx.fillStyle = PALETTE.ink;
  ctx.fillRect(px(o.x + o.w * 0.08), px(o.y + o.h - 16), o.w * 0.14, 8);
  ctx.restore();
}

function drawUmbrellaObstacle(ctx, o) {
  if (images.umbrella) {
    ctx.drawImage(images.umbrella, px(o.x), px(o.y), o.w, o.h);
    return;
  }
  ctx.save();
  // Pole
  ctx.fillStyle = PALETTE.ink;
  ctx.fillRect(px(o.x + o.w / 2 - 2), px(o.y + 20), 4, o.h - 20);
  // Parasol canopy
  ctx.fillStyle = PALETTE.flare;
  ctx.fillRect(px(o.x), px(o.y), o.w, 14);
  ctx.fillStyle = PALETTE.sun;
  ctx.fillRect(px(o.x + 6), px(o.y + 4), o.w - 12, 6);
  // Sunbather sitting beneath
  ctx.fillStyle = PALETTE.sand;
  ctx.fillRect(px(o.x + o.w * 0.2), px(o.y + o.h - 20), o.w * 0.6, 16);
  ctx.restore();
}

// single = sunbather on a mat, umbrella = taller with parasol.
export function drawObstacle(ctx, o) {
  ctx.imageSmoothingEnabled = false;
  if (o.type === "umbrella") {
    drawUmbrellaObstacle(ctx, o);
  } else {
    drawSingleObstacle(ctx, o);
  }
}

function drawGemCollectible(ctx, o) {
  const cx = px(o.x + o.w / 2);
  const cy = px(o.y + o.h / 2);
  const r = Math.min(o.w, o.h) / 2;
  ctx.save();
  ctx.fillStyle = PALETTE.arcade;
  ctx.beginPath();
  ctx.moveTo(cx, cy - r);
  ctx.lineTo(cx + r, cy);
  ctx.lineTo(cx, cy + r);
  ctx.lineTo(cx - r, cy);
  ctx.fill();
  ctx.fillStyle = PALETTE.foam;
  ctx.fillRect(px(cx - 2), px(cy - r * 0.4), 4, 4);
  ctx.restore();
}

function drawStarCollectible(ctx, o) {
  const cx = px(o.x + o.w / 2);
  const cy = px(o.y + o.h / 2);
  const r = Math.min(o.w, o.h) / 2;
  ctx.save();
  ctx.fillStyle = PALETTE.sun;
  // Chunky pixel-star: a vertical + horizontal bar plus a diamond core.
  ctx.fillRect(px(cx - 2), px(cy - r), 4, r * 2);
  ctx.fillRect(px(cx - r), px(cy - 2), r * 2, 4);
  ctx.fillStyle = PALETTE.flare;
  ctx.fillRect(px(cx - 3), px(cy - 3), 6, 6);
  ctx.restore();
}

function drawShellCollectible(ctx, o) {
  const cx = px(o.x + o.w / 2);
  const cy = px(o.y + o.h / 2);
  const r = Math.min(o.w, o.h) / 2;
  ctx.save();
  ctx.fillStyle = PALETTE.sand;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = PALETTE.grape;
  for (let i = -1; i <= 1; i++) {
    ctx.fillRect(px(cx + i * 4 - 1), px(cy - r * 0.5), 2, r);
  }
  ctx.restore();
}

const COLLECTIBLE_DRAWERS = [drawGemCollectible, drawStarCollectible, drawShellCollectible];

// Procedural collectible per item.kind (0=gem, 1=star, 2=shell — 3 distinct
// little shapes/colors from PALETTE). Swap point: images["item_" + kind].
export function drawCollectible(ctx, item) {
  ctx.imageSmoothingEnabled = false;
  const name = "item_" + item.kind;
  if (images[name]) {
    ctx.drawImage(images[name], px(item.x), px(item.y), item.w, item.h);
    return;
  }
  const draw = COLLECTIBLE_DRAWERS[item.kind] || drawGemCollectible;
  draw(ctx, item);
}
