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
- `frontend/src/components/match3d/` is the presentation (played at `GAME_SPEED`, 85% of real time). It reads the state
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

- The pitch's lines are not a mesh: `mcLines` in `stadium.ts` is a distance field
  in the turf shader, so the paint takes the grass's blades, light and shadows.

## Controls

The same hands as «Ответка»: `Controls.tsx` uses `Stick` and `Finger` from
`lib/oneOnOne/gesture` and the layout of `AttackRun`. The left half is a
floating stick, and its rim is the sprint. On the right, the big button shoots:
a tap is a quick shot, a hold adds power, a swipe up is the finesse, a sideways
flick is the feint. The stick's lean picks the corner. Round it are «Пас»,
«Разрез» and «Навес» («Парашют» in front of goal). Without the ball the same
places are «Отбор», «Смена» and «Подкат». «Смена» and «Подкат» are all the defence needs: the second man goes by himself. A computer can use WASD or
arrows, Shift to sprint, J shot, K pass, L through ball, I cross, U feint,
H tackle, G slide, Q switch.

Who is in charge of the man (the rule all the help below obeys): a moving thumb
always steers. A thumb that was already down when the game changed his man is
locked out (`toMan`, `readStick`) until it moves or lifts, because it was
steering somebody else; locked or idle, the man plays by himself exactly as a
team-mate does, tackling included. Steering roughly at a loose ball steers at
the ball.

The help a human gets, all in `engine.ts`:

- `bestMate` takes the stick for a direction and, in it, the man with a clear
  lane. A white ring on the pitch shows him (`passTarget`).
- A ball on its way to the human's man is his: `receiver`. The man runs to meet
  it unless a new thumb says otherwise (`meetPoint`), and a rolling ball bends on to him
  and keeps its pace until he has it (`assistPass`). The AI gets none of this.
- When the keeper has it in his hands the human has the keeper: the stick aims,
  «Пас» rolls or throws, «Навес» and «Выбить» go long, and after six seconds the
  keeper decides himself. Goal kicks work the same way.
- With the ball theirs or loose, the human gets the man nearest to where it is
  going within a fifth of a second of that changing (`userAutoSwitch`). «Смена»
  by hand holds for three quarters of a second.
- A touch on a team-mate plays the best ball to him (`bestBall`: in behind if
  he is off and running, on the ground if the lane is open, otherwise over the
  top). Without the ball the same touch makes him the human's man.

Long balls: a man with nobody on him brings a high ball down off the chest or the
thigh however hot it is, and waits for one that is dropping; the man it was hit to
has the better of a real jump, and a header goes on to a team-mate when one is
there. Grass kills a landing ball (`BOUNCE_FRICTION`, `planLob` hangs it longer).
Out of the keeper's hands a throw or a punt goes over a man standing in front of
him, and a keeper picks a way past that man (`inHisWay`).

Without the ball the side plays zones (`thinkTeam`): one presses, one covers, two
at most near their own goal, and everyone else picks up the most dangerous free man
measured from his zone, not from where he stands, and doesn't leave it. With the
ball men keep apart (`chooseRun`), wingers hold both touchlines, runs go into the
gap in the back line (`channel`), a full-back overlaps on the ball's side, and when
the ball's side is crowded the far flank gets a switch: for the human «Навес» with the
stick across (`bestMate` with `air`). `bench/shape.mjs` measures all of this.

Penalties and close free kicks: when the human's team has a penalty, or a free
kick under 30 m out and under 20 m wide, and when he faces a penalty, the match
stops at the whistle (`set.scene`, `sceneOf`) and the kick is played in the game's
swipe scene (`SetPieceScene`, `createSetup` from the foul's real spot, the keeper of
«Пенальти» for their penalty). Only the outcome comes back as an input
(`Press` "scene"): a goal counts, a save is in the keeper's hands, a miss is a goal
kick, off the wall the ball is loose. No replay of such a goal. If the scene can't
run, the kick is played in the match. For a server replay the swipe itself will
have to be kept: today nothing rewarded depends on it.

Stamina (`Player.stamina`): the ring under the human's man is the gauge. Ten seconds of sprint
empties it, twelve of walking fills it, and tired legs lose a sixth of the top speed.
At a sprint the ball runs further from the foot, the turns get wider and feints
stop selling: dribbling is done at walking pace.

## The team

With the ball deep in its own third a side takes up `buildSpot`: the centre-backs
split to the edges of the box, the holding man drops between them, the
full-backs go high and wide, the midfield offers in the half-spaces and the
front men pin the line. A goal kick starts from that shape, short when somebody
is really free and long over the press when not. In the attacking third, with
the ball wide, the box fills: near post, far post, spot, edge. Crosses hit into
a man closing down deflect, usually behind, and that is where corners come from.

In their third the side without the ball presses (`pressingHigh`): it stretches,
everyone in front of the back four takes a man, and the two nearest go at once
for 2.5 seconds after losing it (`lostAt`). It backs off when the keeper has the
ball in his hands. Elsewhere it holds the block below.

Without the ball (`blockSpot`) a side is three flat lines 13 metres apart that
slide together: `backLine` follows the ball, `LINE_GAP` places the rest, and
nobody follows a man out of his zone except inside the box. Anybody the ball
comes within 4.5 m of steps in and tackles by himself (`thinkTackle`), the human's
side like the other, and close to goal two go. A carrier who runs into a body
gives way and loses pace (the keep-apart in `stepPlayers`). Who is ahead of his
place when the ball goes runs back flat out (`recover`). With the ball the
forwards start runs in behind from the line (`Player.dash`): a pass that comes
late finds them offside. After a goal `lineUp` puts everybody on his spot.

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
how close the human's man stays to the action. `bench/audit.mjs` judges AI against
AI the way a match is judged: spells of possession, duels, what each kind of
kick keeps. `bench/out/board.html` (with `engine.iife.js` built beside it) draws
the match from above, twelve moments at a time.

## Before rewards

Rewards and limits need agreed numbers in `GameConfig`, the counter pairs on
`User` with a migration, and the server replay in V8. A new mode also goes into
`admin_analytics_service.MODE_SOURCES`.
