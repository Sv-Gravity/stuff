// All gameplay tuning in one place.
export const CFG = {
  TICK: 1 / 30,            // fixed simulation step (seconds)
  WORLD_W: 3000,
  WORLD_H: 2000,

  ANT_R: 5,                // collision radius of a stickman
  ANT_SPEED: 125,          // walking speed (world units / s)
  CRUMB_CARRY_SLOW: 0.8,
  PUDDLE_SLOW: 0.5,
  VISION: 270,             // how far you can see

  ROUND_TIME: 75,          // seconds per round
  WIN_POINTS: 3,           // first side to this many points wins the match
  COUNTDOWN: 3,
  INTERMISSION: 5,

  // The big food. Net push (sum of every carrier's push vector, each up to 1)
  // must beat its friction before it moves at all.
  FOOD_K: 28,              // speed per unit of net push above friction
  FOOD_MAX_SPEED: 70,
  GRAB_RANGE: 12,

  CRUMBS: 16,
  CRUMB_TIME: 4,           // seconds added to the clock per crumb brought home

  // Traitor
  TRIP_RANGE: 30,
  TRIP_COOLDOWN: 9,
  TRIP_STUN: 1.7,

  // Accusations
  VOTE_RANGE: 55,
  WRONG_WEB_TIME: 12,      // an innocent ant that gets voted out is webbed this long
};

export const NO_INPUT = Object.freeze({ mx: 0, my: 0, grab: false, act: false, vote: false });
