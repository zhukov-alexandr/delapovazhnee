// Pure collectible system: spawning, scrolling, catching. No rendering.
import { GAME } from "./config.js";
import { collides } from "./obstacles.js";

export function createCollectibleState() {
  return { items: [], timeToNext: 1.2, elapsed: 0 };
}

// Randomized gap (seconds) for spawning collectibles.
function nextGap() {
  return GAME.ITEM_MIN_GAP + Math.random() * (GAME.ITEM_MAX_GAP - GAME.ITEM_MIN_GAP);
}

// Weighted kind pick: each of the (ITEM_KINDS-1) normal kinds has weight
// ITEM_SPECIAL_RARITY; the special kind has weight 1, so it spawns that many
// times less often than any single normal kind.
function pickKind() {
  const normals = GAME.ITEM_KINDS - 1;
  const total = normals * GAME.ITEM_SPECIAL_RARITY + 1;
  const r = Math.random() * total;
  if (r < normals * GAME.ITEM_SPECIAL_RARITY) {
    return Math.floor(r / GAME.ITEM_SPECIAL_RARITY);
  }
  return GAME.ITEM_SPECIAL_KIND;
}

function spawn(state, worldW) {
  const kind = pickKind();
  const y = GAME.ITEM_Y_MIN + Math.random() * (GAME.ITEM_Y_MAX - GAME.ITEM_Y_MIN);
  state.items.push({
    x: worldW + 20,
    y: y,
    w: GAME.ITEM_W,
    h: GAME.ITEM_H,
    kind: kind,
    caught: false,
  });
}

// Advance collectibles: spawn over time, scroll left, drop off-screen.
// worldW defaults large so the pure self-test (no canvas) still spawns/moves sanely.
export function stepCollectibles(state, dt, worldW = 640, speed = GAME.RUN_SPEED) {
  state.elapsed += dt;

  state.timeToNext -= dt;
  if (state.timeToNext <= 0) {
    spawn(state, worldW);
    state.timeToNext = nextGap();
  }

  // Move items left at scroll speed.
  for (const item of state.items) {
    item.x -= speed * dt;
  }

  // Drop off-screen items.
  state.items = state.items.filter((item) => item.x + item.w > -40);
}

// Check runner box against all items. Mark caught, remove them, and return
// { points, special }: points sums the value of everything caught this frame
// (+1 per normal kind, +ITEM_SPECIAL_POINTS for the bonus item); special is
// true if the bonus item was among them (game.js uses it to start the grow).
export function catchCollectibles(runnerBox, state) {
  let points = 0;
  let special = false;
  const uncaught = [];
  for (const item of state.items) {
    if (collides(runnerBox, item)) {
      item.caught = true;
      if (item.kind === GAME.ITEM_SPECIAL_KIND) {
        points += GAME.ITEM_SPECIAL_POINTS;
        special = true;
      } else {
        points += 1;
      }
    } else {
      uncaught.push(item);
    }
  }
  state.items = uncaught;
  return { points, special };
}
