// Pure game progression: composes physics + obstacles into one advance step.
// No DOM — node-testable.
import { createRunner, stepRunner } from "./physics.js";
import { createGameState, stepObstacles, collides, runnerBox } from "./obstacles.js";
import { createCollectibleState, stepCollectibles, catchCollectibles } from "./collectibles.js";

export function createGame() {
  return { runner: createRunner(), obs: createGameState(), col: createCollectibleState(), state: "menu", score: 0, caught: 0 };
}
export function startGame(g, speedMult = 1) {
  g.runner = createRunner(); g.obs = createGameState(speedMult); g.col = createCollectibleState(); g.score = 0; g.caught = 0; g.state = "running";
}

// Pure lyric-reveal helper (Task 23): every N points crosses a threshold that
// reveals the next song line. `revealed` is how many lines are already shown;
// returns the index to reveal next, or null if no new line is due yet.
export function nextRevealIndex(score, n, revealed, total) {
  if (n > 0 && revealed < total && Math.floor(score / n) > revealed) {
    return revealed;
  }
  return null;
}

// Advance one frame. Returns {over, scoreDelta}. No-op unless running.
// `invulnerable` (post-life-loss grace, game.js) skips collision so the runner
// passes through the obstacle that just hit it instead of instantly dying again.
export function stepGame(g, dt, worldW, invulnerable = false) {
  if (g.state !== "running") return { over: false, scoreDelta: 0 };
  stepRunner(g.runner, dt);
  const before = g.obs.score;
  stepObstacles(g.obs, dt, worldW);
  const obstacleDelta = g.obs.score - before;
  stepCollectibles(g.col, dt, worldW, g.obs.speed);
  const box = runnerBox(g.runner);
  const { points, special } = catchCollectibles(box, g.col);
  g.caught += points;
  g.score = g.obs.score + g.caught;
  const scoreDelta = obstacleDelta + points;
  if (!invulnerable) {
    for (const o of g.obs.obstacles) {
      if (collides(box, o)) { g.state = "over"; return { over: true, scoreDelta, grew: special }; }
    }
  }
  return { over: false, scoreDelta, grew: special };
}
