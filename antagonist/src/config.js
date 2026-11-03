// All gameplay tuning in one place.
export const CFG = {
  TICK: 1 / 60,            // fixed simulation step (seconds)
  WORLD_W: 3000,
  WORLD_H: 2000,

  ANT_R: 5,                // collision radius of a stickman
  ANT_SPEED: 125,          // walking speed (world units / s)
  CRUMB_CARRY_SLOW: 0.8,
  PUDDLE_SLOW: 0.5,
  VISION: 270,             // how far you can see

  ROUND_TIME: 70,          // seconds per round
  WIN_POINTS: 3,           // first side to this many points wins the match
  COUNTDOWN: 3,
  INTERMISSION: 12,        // round-end replay; skipped early once every human is ready

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

  // Antennae meeting: freezes everyone, the clock keeps running.
  MEETING_TIME: 20,
  MEETING_MIN_ROUND_T: 8,  // can't call one in the first seconds of a round

  // Scent pings. Finding the food releases a real scent everyone can follow;
  // the traitor can plant fake ones that look identical.
  FAKE_SCENTS: 2,          // per round
  FAKE_SCENT_COOLDOWN: 20,
  DEBUNK_RANGE: 150,       // an honest ant this close to a fake scent exposes it

  REPLAY_EVERY: 6,         // ticks between replay frames
};

export const NO_INPUT = Object.freeze({ mx: 0, my: 0, grab: false, act: false, vote: false, meet: false, scent: false, mvote: undefined, say: undefined, ready: false });
