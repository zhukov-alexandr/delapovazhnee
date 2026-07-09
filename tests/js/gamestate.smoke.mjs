import { GAME } from "../../static/js/config.js";
import { createGame, startGame, stepGame } from "../../static/js/gamestate.js";

let failed = 0;
const ok = (c, m) => { if (c) console.log("PASS " + m); else { failed++; console.error("FAIL " + m); } };

// Not running -> no-op.
const g0 = createGame();
const r0 = stepGame(g0, 1 / 60, 640);
ok(r0.over === false && g0.state === "menu", "stepGame is a no-op before start");

// Collision -> over.
const g1 = createGame(); startGame(g1);
g1.obs.obstacles.push({ x: GAME.RUNNER_X, y: GAME.GROUND_Y - 26, w: 44, h: 26, type: "single", passed: false });
const r1 = stepGame(g1, 1 / 60, 640);
ok(r1.over === true && g1.state === "over", "collision ends the run");

// Invulnerable (post-life-loss grace) -> the same overlap does NOT end the run.
const g1b = createGame(); startGame(g1b);
g1b.obs.obstacles.push({ x: GAME.RUNNER_X, y: GAME.GROUND_Y - 26, w: 44, h: 26, type: "single", passed: false });
const r1b = stepGame(g1b, 1 / 60, 640, true);
ok(r1b.over === false && g1b.state === "running", "invulnerable skips collision (pass-through grace)");

// Score increments when an obstacle passes the runner. Place it LEFT of the runner's
// x-lane (right edge < RUNNER_X) so it scores this tick WITHOUT colliding — a standing
// runner's box overlaps any obstacle in its own lane, so we must avoid the lane here.
// Coordinates are relative to RUNNER_X so the fixture holds if RUNNER_X is retuned.
const g2 = createGame(); startGame(g2);
g2.obs.obstacles.push({ x: GAME.RUNNER_X - 50, y: GAME.GROUND_Y - 26, w: 44, h: 26, type: "single", passed: false });
const r2 = stepGame(g2, 1 / 60, 640);
ok(r2.scoreDelta >= 1 && g2.score >= 1 && r2.over === false, "score increments when an obstacle passes");

// Catching an item raises score without setting over. Place an item overlapping an airborne runner.
const g3 = createGame(); startGame(g3);
g3.runner.y = 170; // airborne
g3.col.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: 0, caught: false });
const r3 = stepGame(g3, 1 / 60, 640);
ok(r3.scoreDelta >= 1 && g3.score >= 1 && r3.over === false, "catching an item raises score without ending game");

// Catching the special (5th) item scores +ITEM_SPECIAL_POINTS and flags grew.
const g4 = createGame(); startGame(g4);
g4.runner.y = 170; // airborne
const before4 = g4.score;
g4.col.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: GAME.ITEM_SPECIAL_KIND, caught: false });
const r4 = stepGame(g4, 1 / 60, 640);
ok(r4.grew === true && (g4.score - before4) >= GAME.ITEM_SPECIAL_POINTS && r4.over === false,
   "special item: +5 score and grew flag, no game over");

if (failed) { console.error(`GAMESTATE SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("GAMESTATE SMOKE: ALL PASS");
