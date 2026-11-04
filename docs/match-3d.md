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
- Phones cap a texture's side at 4096, and the clips run past that as one
  column. So the bake is an atlas of frames side by side (`Baked.columns`). A
  texture over the cap fails silently: every bone is zero and the people
  collapse to a point.
- `dragback` ends turned 180°. While it plays the body's heading waits
  (`Motion.turning`), and the switch at its end is a cut, not a blend.

## Controls

The same hands as «Ответка»: `Controls.tsx` uses `Stick` and `Finger` from
`lib/oneOnOne/gesture` and the layout of `AttackRun`. The left half is a
floating stick, and its rim is the sprint. On the right, the big button shoots:
a tap is a quick shot, a hold adds power, a swipe up is the finesse, a sideways
flick is the feint. The stick's lean picks the corner. Round it are «Пас»,
«Разрез» and «Навес» («Парашют» in front of goal). Without the ball the same
places are «Отбор», «Смена», «Подкат» and «Прессинг». A computer can use WASD or
arrows, Shift to sprint, J shot, K pass, L through ball, I cross, U feint,
H tackle, G slide, Q switch.

The help a human gets, all in `engine.ts`:

- `bestMate` takes the stick for a direction and, in it, the man with a clear
  lane. A white ring on the pitch shows him (`passTarget`).
- A ball on its way to the human's man is his: `receiver`. The man runs to meet
  it whatever the stick does (`meetPoint`), and a rolling ball bends on to him
  and keeps its pace until he has it (`assistPass`). The AI gets none of this.
- When the keeper has it in his hands the human has the keeper: the stick aims,
  «Пас» rolls or throws, «Навес» and «Выбить» go long, and after six seconds the
  keeper decides himself. Goal kicks work the same way.
- With the ball theirs or loose, the human gets the man nearest to where it is
  going within a fifth of a second of that changing (`userAutoSwitch`). «Смена»
  by hand holds for three quarters of a second.

Stamina (`Player.stamina`, a bar over the man): ten seconds of sprint empties
it, twelve of walking fills it, and tired legs lose a sixth of the top speed.
At a sprint the ball runs further from the foot, the turns get wider and feints
stop selling: dribbling is done at walking pace.

## Testing on a phone

`bench/serve.mjs` serves `bench/out` with the app's public assets, and
`src/bench/match3d/play.tsx` is the match on its own. It reports fps, dpr and
draw calls to `bench/results` every 15 seconds.

```bash
npx esbuild src/bench/match3d/play.tsx --bundle --minify --format=esm --target=es2020 --jsx=automatic --tsconfig=tsconfig.json --outfile=bench/out/play.js
```

`bench/sim.mjs` plays AI against AI without a screen and prints the statistics
used to tune the football. `bench/human.mjs` plays through `Input` as a thumb
does and prints how many passes arrive, what happens to the keeper's ball and
how close the human's man stays to the action.

## Before rewards

Rewards and limits need agreed numbers in `GameConfig`, the counter pairs on
`User` with a migration, and the server replay in V8. A new mode also goes into
`admin_analytics_service.MODE_SOURCES`.
