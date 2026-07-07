// Pure vertical physics for the runner. No DOM, no canvas — unit-testable.
import { GAME } from "./config.js";

export function createRunner() {
  return { y: GAME.GROUND_Y, vy: 0, onGround: true, jumps: 0 };
}

// Trigger a jump: first from ground, second (higher) allowed mid-air, max 2.
// vMult scales the launch velocity (used to jump higher while grown).
export function jump(runner, vMult = 1) {
  if (runner.jumps === 0) {
    runner.vy = GAME.JUMP_V * vMult;
    runner.onGround = false;
    runner.jumps = 1;
  } else if (runner.jumps === 1) {
    runner.vy = GAME.DOUBLE_JUMP_V * vMult;
    runner.jumps = 2;
  }
}

// Integrate one frame of gravity; clamp to ground and reset jump count on landing.
export function stepRunner(runner, dt) {
  runner.vy += GAME.GRAVITY * dt;
  runner.y += runner.vy * dt;
  if (runner.y >= GAME.GROUND_Y) {
    runner.y = GAME.GROUND_Y;
    runner.vy = 0;
    runner.onGround = true;
    runner.jumps = 0;
  }
}
