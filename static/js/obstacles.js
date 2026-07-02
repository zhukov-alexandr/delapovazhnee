// Pure obstacle system: spawning, scrolling, collision, scoring. No rendering.
import { GAME } from "./config.js";

const SINGLE = { w: 44, h: 26 };   // sunbather on a mat — clear with single jump
const UMBRELLA = { w: 52, h: 78 };  // sunbather with umbrella — needs double jump

// speedMult scales both the starting speed and the ramp cap (server-tunable
// via /api/config, Task 21/23). Defaults to 1 so existing callers/tests are
// unaffected.
export function createGameState(speedMult = 1) {
  return {
    obstacles: [],
    speed: GAME.RUN_SPEED * speedMult,
    timeToNext: 1.2,
    elapsed: 0,
    score: 0,
    speedMult,
  };
}

// Balanced randomized gap (seconds) that tightens slightly as speed grows.
function nextGap(speed) {
  const base = Math.max(0.9, 1.8 - (speed - GAME.RUN_SPEED) / 500);
  return base + Math.random() * 0.9;
}

function spawn(state, worldW) {
  const umbrella = Math.random() < 0.35;
  const dim = umbrella ? UMBRELLA : SINGLE;
  state.obstacles.push({
    x: worldW + 20, y: GAME.GROUND_Y - dim.h, w: dim.w, h: dim.h,
    type: umbrella ? "umbrella" : "single", passed: false,
  });
}

// worldW defaults large so the pure self-test (no canvas) still spawns/moves sanely.
export function stepObstacles(state, dt, worldW = 640) {
  state.elapsed += dt;
  const maxSpeed = GAME.MAX_SPEED * (state.speedMult || 1);
  state.speed = Math.min(maxSpeed, state.speed + GAME.SPEED_RAMP * dt);

  state.timeToNext -= dt;
  if (state.timeToNext <= 0) {
    spawn(state, worldW);
    state.timeToNext = nextGap(state.speed);
  }

  for (const o of state.obstacles) {
    o.x -= state.speed * dt;
    if (!o.passed && o.x + o.w < GAME.RUNNER_X) {
      o.passed = true;
      state.score += 1;
    }
  }
  state.obstacles = state.obstacles.filter((o) => o.x + o.w > -40);
}

export function runnerBox(runner) {
  return { x: GAME.RUNNER_X, y: runner.y - GAME.RUNNER_H, w: GAME.RUNNER_W, h: GAME.RUNNER_H };
}

export function collides(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}
