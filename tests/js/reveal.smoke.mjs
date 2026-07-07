// Headless smoke test for the pure lyric-reveal helper (Task 23).
import { nextRevealIndex } from "../../static/js/gamestate.js";

let failed = 0;
const ok = (c, m) => { if (c) console.log("PASS " + m); else { failed++; console.error("FAIL " + m); } };

const n = 5;
const total = 12; // song «19» has 12 lines (see lyrics.js)

ok(nextRevealIndex(n, n, 0, total) === 0, "score==n, revealed=0 -> reveals index 0");
ok(nextRevealIndex(2 * n, n, 1, total) === 1, "score==2n, revealed=1 -> reveals index 1");
ok(nextRevealIndex(n - 1, n, 0, total) === null, "score below n -> null");
ok(nextRevealIndex(1000, n, total, total) === null, "revealed==total -> null, even at high score");
ok(nextRevealIndex(100, 0, 0, total) === null, "n=0 -> null (reveal mechanic disabled)");

if (failed) { console.error(`REVEAL SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("REVEAL SMOKE: ALL PASS");
