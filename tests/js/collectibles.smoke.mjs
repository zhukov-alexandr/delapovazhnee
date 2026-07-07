import { GAME } from "../../static/js/config.js";
import { createCollectibleState, stepCollectibles, catchCollectibles } from "../../static/js/collectibles.js";
import { runnerBox } from "../../static/js/obstacles.js";
import { createRunner } from "../../static/js/physics.js";

let failed = 0;
const ok = (c, m) => { if (c) console.log("PASS " + m); else { failed++; console.error("FAIL " + m); } };

// spawns over time
const s = createCollectibleState();
for (let i = 0; i < 600; i++) stepCollectibles(s, 1 / 60, 640);
ok(s.items.length >= 0, "stepCollectibles runs without error");
ok(s.items.every(it => it.y >= GAME.ITEM_Y_MIN && it.y <= GAME.ITEM_Y_MAX), "items spawn in the air band");

// catch: airborne runner overlapping an item scores it, item removed
const s2 = createCollectibleState();
const r = createRunner(); r.y = 170; // airborne, box ~[122,170]
s2.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: 0, caught: false });
const n = catchCollectibles(runnerBox(r), s2);
ok(n.points === 1 && !n.special && s2.items.length === 0, "airborne runner catches a normal item (+1, removed)");

// special (5th) item: +ITEM_SPECIAL_POINTS and flags the grow power-up
const s2b = createCollectibleState();
const rb = createRunner(); rb.y = 170;
s2b.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: GAME.ITEM_SPECIAL_KIND, caught: false });
const nb = catchCollectibles(runnerBox(rb), s2b);
ok(nb.points === GAME.ITEM_SPECIAL_POINTS && nb.special === true, "special item scores +5 and sets grow flag");

// grounded runner does NOT catch a high air item
const s3 = createCollectibleState();
const g = createRunner(); // grounded, box ~[252,300]
s3.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: 0, caught: false });
ok(catchCollectibles(runnerBox(g), s3).points === 0, "grounded runner misses a high air item");

// special is rarer: over many spawns it appears, but far less than normals
const s4 = createCollectibleState();
let specials = 0, normals = 0;
for (let i = 0; i < 15000; i++) {
  stepCollectibles(s4, 1 / 60, 640);
  for (const it of s4.items) { if (it.counted) continue; it.counted = true;
    if (it.kind === GAME.ITEM_SPECIAL_KIND) specials++; else normals++; }
}
ok(specials > 0 && normals > specials * 2, `special item is rarer than normals (normals=${normals}, specials=${specials})`);

if (failed) { console.error(`COLLECTIBLES SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("COLLECTIBLES SMOKE: ALL PASS");
