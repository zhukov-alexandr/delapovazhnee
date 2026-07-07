// Pure obstacle system: spawning, scrolling, collision, scoring. No rendering.
import { GAME } from "./config.js";

// Collision box for an obstacle sprite of the given aspect: OBSTACLE_H tall with
// width from the aspect, but if that width exceeds OBSTACLE_MAX_W the whole box
// shrinks (keeping the aspect) so the widest sprites stay jumpable. `scale`
// (default 1) multiplies the final box for deliberately bigger obstacles.
function obstacleBox(aspect, scale = 1) {
  let h = GAME.OBSTACLE_H;
  let w = Math.round(h * aspect);
  if (w > GAME.OBSTACLE_MAX_W) {
    w = GAME.OBSTACLE_MAX_W;
    h = Math.round(w / aspect);
  }
  return { w: Math.round(w * scale), h: Math.round(h * scale) };
}

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

// Gap (seconds) to the next obstacle: a speed-dependent nominal spacing (tightens
// as speed grows; nominal = the previous formula's average), randomized to
// 70%–130% of that nominal so the distance between obstacles varies.
function nextGap(speed) {
  const nominal = Math.max(1.35, 2.25 - (speed - GAME.RUN_SPEED) / 500);
  return nominal * (0.7 + Math.random() * 0.6);
}

// Pick a random obstacle sprite from GAME.OBSTACLES and spawn it ground-anchored.
// `sprite` is the images[] key (obs_<index>) the renderer draws.
function spawn(state, worldW) {
  const kinds = GAME.OBSTACLES;
  const j = Math.floor(Math.random() * kinds.length);
  const { w, h } = obstacleBox(kinds[j].aspect, kinds[j].scale);
  state.obstacles.push({
    x: worldW + 20, y: GAME.GROUND_Y - h, w, h,
    sprite: "obs_" + j, passed: false,
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
