// Shared game constants. Units: logical world pixels; y grows downward.
export const GAME = {
  WORLD_H: 360,          // fixed logical height; width comes from viewport
  MIN_VIEW_W: 500,       // camera (game.js resize()): minimum visible world width in
                         // logical px — on narrow/tall mobile this caps zoom-in so the
                         // runner (RUNNER_X=90) keeps track ahead instead of sitting
                         // centered. Tuning value; adjust to taste, does not affect
                         // obstacle/collision logic.
  GROUND_Y: 300,         // runner baseline (top of feet band)
  GRAVITY: 2600,         // px/s^2
  JUMP_V: -760,          // px/s initial velocity, single jump
  DOUBLE_JUMP_V: -900,   // px/s for the second (air) jump — STRONGER than JUMP_V so the
                         // air jump (which resets vy) reaches a clearly higher apex
  RUN_SPEED: 260,        // starting world scroll speed px/s
  SPEED_RAMP: 3.5,       // px/s added per second survived
  MAX_SPEED: 560,        // speed cap
  RUNNER_W: 34,
  RUNNER_H: 48,
  RUNNER_X: 90,          // fixed horizontal position of the runner
  ITEM_W: 60,
  ITEM_H: 60,
  ITEM_KINDS: 3,
  ITEM_MIN_GAP: 1.6,
  ITEM_MAX_GAP: 3.2,
  ITEM_Y_MIN: 120,       // top-y band; kept high enough that a 60px item's bottom stays
  ITEM_Y_MAX: 180,       // above the grounded runner (GROUND_Y-RUNNER_H..GROUND_Y) — catch by jumping
};
