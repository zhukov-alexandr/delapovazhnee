// Shared game constants. Units: logical world pixels; y grows downward.
export const GAME = {
  WORLD_H: 360,          // fixed logical height; width comes from viewport
  MIN_VIEW_W: 360,       // camera (game.js resize()): minimum visible world width in
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
  ITEM_KINDS: 5,         // kinds 0..3 are normal (+1); kind 4 is the rare bonus item
  ITEM_SPECIAL_KIND: 4,  // the 5th item: +5 points and a timed "grow" power-up
  ITEM_SPECIAL_POINTS: 5,
  ITEM_SPECIAL_RARITY: 3, // the special is 3x less likely to spawn than each normal kind
  BASE_SCALE: 1.2,       // normal runner draw size (1.2 = 20% bigger than the sprite box)
  GROW_TIME: 10,         // seconds the runner stays big after the bonus item
  GROW_SCALE: 2,         // grown draw size (absolute 2x of the box, unchanged by BASE_SCALE)
  ITEM_MIN_GAP: 1.6,
  ITEM_MAX_GAP: 3.2,
  ITEM_Y_MIN: 120,       // top-y band; kept high enough that a 60px item's bottom stays
  ITEM_Y_MAX: 180,       // above the grounded runner (GROUND_Y-RUNNER_H..GROUND_Y) — catch by jumping
  MAX_LIVES: 3,          // hearts; each obstacle hit costs one life (game.js)
  INVULN_TIME: 1.4,      // seconds of pass-through grace after losing a life, so
                         // resuming doesn't instantly re-hit the same obstacle
};

// Presave modal (Task 26): band.link identifiers + the streaming services
// listed as rows in the modal, in display order. Services + order match the
// original band.link page (dnkmusic.ru/devyatnadtsat) — verified by rendering
// it. КИОН Музыка is band.link type "mts". See boot.js openPresave() for how
// each service's presave URL is built (they are NOT uniform).
export const PRESAVE = {
  HASH: "ywthC",
  UPC: "4610605713098",
  // Spotify uses band.link's own static OAuth client; the return URL is
  // injected into the OAuth `state`, not a redirectUrl param.
  SPOTIFY_CLIENT_ID: "b4a316c64a59474d976ffc5dbf6e25e0",
  SERVICES: [
    { id: "yandex", name: "Яндекс Музыка" },
    { id: "spotify", name: "Spotify" },
    { id: "vkmusic", name: "VK Музыка" },
    { id: "applemusic", name: "Apple Music" },
    { id: "mts", name: "КИОН Музыка" },
  ],
};
