# «Матч 3D»

A short real 11-a-side match in landscape: 80′ to 90′, 0:0, about three and a
half minutes of real time. The human plays the ball carrier and switches
between team-mates. No rewards or limits yet, so the mode costs the economy
nothing and nothing is sent to the server.

## Layers

- `frontend/src/lib/match3d/` is the simulation, three.js-free. `createMatch`
  and `stepMatch(state, input)` are its whole interface, at a fixed 60 Hz.
  `core.ts` holds the state and the ball's physics, `actions.ts` the kicks,
  tackles and feints, `brain.ts` the team shape and the AI, `keeper.ts` the
  goalkeepers, `engine.ts` the tick, the laws and the restarts.
- `frontend/src/components/match3d/` is the presentation. It reads the state
  and feeds one `Input` per tick. `game.ts` runs the loop, the camera, the
  sound and the goal replay, `motion.ts` picks a clip for everybody,
  `baked.ts` and `squad.ts` draw 25 people in a few instanced draws,
  `stadium.ts` is the ground, `Match3DGame.tsx` the controls and the HUD.
- `frontend/public/match-3d/moves.glb` holds the match's own 28 clips. They are
  built by `tools/match-3d` (see its README).

## Rules for the simulation

The engine must stay a pure function of `setup + input per tick`, so that a
later server check can replay a match by running the same JS in embedded V8
rather than keeping a Python port. So in `lib/match3d`:

- only + − × ÷ and `Math.sqrt`: `Math.sin`, `Math.pow` and friends differ
  between engines;
- only the seeded `rnd`, never `Math.random` or the time;
- nothing from the presentation.

`engine.test.ts` checks the determinism and scans the sources for forbidden
calls. Presentation code may use anything: it never feeds the simulation.

## Rendering notes

- Every mesh of `footballer.glb` is quantized on its own, with its scale hidden
  in its inverse bind matrices. `mergeModel` brings them into one space through
  those matrices. Without that the bodies collapse.
- `bakeClips` takes the inverse bind matrices from the file. `skeleton.pose()`
  would rewrite the bones' local scale, and clips key no scale.
- `dragback` ends turned 180°. While it plays the body's heading waits
  (`Motion.turning`), and the switch at its end is a cut, not a blend.

## Controls

The left half of the screen is a floating stick. Hold a kick button for power.
On «Удар», drag sideways for curl and up for a chip. The stick across picks the
corner of the goal. A computer can use WASD or arrows, Shift to sprint, J shot,
K pass, L through ball, I cross, U feint, H tackle, G slide, Q switch.

## Testing on a phone

`bench/serve.mjs` serves `bench/out` with the app's public assets, and
`src/bench/match3d/play.tsx` is the match on its own. It reports fps, dpr and
draw calls to `bench/results` every 15 seconds.

```bash
npx esbuild src/bench/match3d/play.tsx --bundle --minify --format=esm --target=es2020 --jsx=automatic --tsconfig=tsconfig.json --outfile=bench/out/play.js
```

`bench/sim.mjs` plays AI against AI without a screen and prints the statistics
used to tune the football.

## Before rewards

Rewards and limits need agreed numbers in `GameConfig`, the counter pairs on
`User` with a migration, and the server replay in V8. A new mode also goes into
`admin_analytics_service.MODE_SOURCES`.
