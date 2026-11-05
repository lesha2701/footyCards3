# «Ферги Тайм»

The mode's name in the game (route `/play/fergie-time`, picture
`src/assets/games/fergie-time.webp`); the code keeps `match3d`.

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
- The texture has a «7» painted on the back of the shirt. `shirtNumber.ts` covers it
  in the shader with the cloth beside it and draws each man's number from one atlas
  of digits (`squad.ts` per instance, `makePlayer`'s `number` for «Атака 1 на 1» and
  «Ответка»). No branches around its lookups: gradients go wrong at a branch's edge.
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

Dribbling: the ball leaves the foot once a stride cycle at a run (`RUN_CYCLE`, 2.95 m,
what the run and sprint clips cover) and once a step at a walk (`stepCarried`:
`touch` / `touchLen`, the side from `touchFoot`). Between touches it rolls: from where
the last touch left it (`touchX/Z`) to where his foot will be for the next, quick off
the foot and dying away (`ROLL_DIES`). It is never tied to the man, so when he turns
its line bends instead of the ball jumping round him. With the ball a man under
`WALK_DRIBBLE` plays the dribble clip, above it the ordinary run and sprint at their
true pace, and `lockStride` (`motion.ts`) keeps the clip's phase on the touch so that
the foot is at the ball when it goes. Two more clips of a run with the ball were not
needed for this; feet no longer skate because `paces` are the clips' measured ones.

The keeper at his feet: a team-mate's ball on the ground is a back pass, not a shot.
He meets it, plays it with his feet (no hands) and is an ordinary man from then on:
he is the human's, runs, feints and passes. «Удар» from him is a long ball to a
team-mate. On the ball he goes no nearer than 3 m to his own line (`KEEPER_LINE`):
the thumb is usually still held back from the pass.

The keeper reads a ball only in its last second (`READ_FROM`). Before that he moves
into line, so a long ball doesn't bring him down while it is still far away.

The buttons: with the ball theirs on someone's feet, or rolling to one of theirs,
they are «Отбор», «Подкат», «Смена». Anything loose or in the air is a ball to play,
so it's «Удар», «Пас», «Разрез», «Навес», headers included.

A corner shows the ball going out for 0.6 s, then cuts to everybody in place
(`cutToCorner`, event "cut"): nobody runs the length of the line.

Long balls: a man with nobody on him brings a high ball down off the chest or the
thigh however hot it is, and waits for one that is dropping; the man it was hit to
has the better of a real jump, and a header goes on to a team-mate when one is
there. Grass kills a landing ball (`BOUNCE_FRICTION`, `planLob` hangs it longer).
Out of the keeper's hands a throw or a punt goes over a man standing in front of
him, and a keeper picks a way past that man (`inHisWay`).

Without the ball the side plays zones (`thinkTeam`): one presses, one covers, two
at most near their own goal, and everyone else picks up the most dangerous free man
measured from his zone, not from where he stands, and doesn't leave it. With the
ball the team goes up with it (`shapeSpot`: `block`, level with the ball past halfway),
forwards and midfielders also get the free places in and around their box as offers
(`BOX_DEPTHS` × `BOX_WIDTHS`, worth what `threat` says, clamped to the offside line)
and sprint there. A cross goes where the freest man is arriving, and everybody within
17 m attacks where it comes down, one at the ball, the others to either side. Men
keep apart (`chooseRun`), wingers hold both touchlines, runs go into the
gap in the back line (`channel`), a full-back overlaps on the ball's side, and when
the ball's side is crowded the far flank gets a switch: for the human «Навес» with the
stick across (`bestMate` with `air`). `bench/shape.mjs` measures all of this.

Pressing with the ball on its way (`want`): as long as no opponent has it or is
about to get a pass, the buttons stay «Удар», «Пас», «Разрез», «Навес», and the press is
played first time when he reaches it, a header included. «Отбор» is only there
against a man on the ball. Feints: a short drag sideways across the big button, with the
stick choosing which one; there is no button of their own.

A duel moves. A tackle is a lunge: until `TACKLE_AT` he drives his weight at where the
ball is about to be (`LUNGE`), and a miss carries him past. Pressed from too far, it
waits up to `TACKLE_WAIT` and goes in as soon as he is in range (`s.tackleT`). The AI
goes in when the ball is off the carrier's foot (`thinkTackle`) and can be beaten by a
feint: a carrier with a man in front of him takes him on (`thinkCarrier`). A slide
plays the middle of the `slide_*` clip over `SLIDE_LEN` (`SLIDE_IN`..`SLIDE_UP`), and
`Getup` with `FROM_SLIDE` plays its end, so he never stands up out of nothing; the
clip's run-up is cut because the man is already running. A ball hit as somebody closes
it down (`b.since < 8`) comes off his shin or gets past him: it doesn't arrive at
his feet, and the AI doesn't pass through the man coming at it.

Who goes at the carrier (`thinkTeam`): only men goal-side of the ball count fully
(`ahead`), and when no midfielder is left in front of him (`screened` false) the back
line steps out, two of them from 16 m outside their goal line's third, instead of
waiting at the box. With the ball coming through the middle the line narrows
(`blockSpot`, `inward`).

Under a press in his own half the AI carrier has the two nearest men coming off the
hunter's line at an angle (`thinkOffBall`), goes over the top when hemmed in, and his
own half is valued by metres gained, so the side doesn't sit there. Its pass goes
before a man flying at him arrives (`closing`). `bench/human.mjs <n> real` plays a
thumb with reaction time; without `real` the script is a perfect chaser.

The keeper close in (`dist` from the kick < 19 m): a reflex, not a read (`p.react`
is short), he has come off his line to cover the goal, and what's near him hits him.

A won tackle really wins it (`stepTackle`): he comes away with it or it squirts his
way, and the man who lost it can't pick it straight back up. A carrier who stands on
the ball (`standing`) gets closed down wherever he is and tackled from any side.

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

The man on the ball (`thinkCarrier`) prices every way of playing it the same way:
`worth` is the chance of it coming off times what the ball is worth there (`threat`),
less the chance of losing it times what losing it there costs (`exposure`). Decisions
are asked ten times a second, so the dice is small (`NOISE`), the way he is already
going counts (`KEEP_GOING`) and with nobody on him he keeps it for 0.7 s (`COMPOSED`).
The longer a side has had it the more through balls, crosses and forward passes are
worth and the less a pass back is (`urge`). `bench/attack.mjs` measures how its spells
end, `bench/log.mjs` prints a stretch of a match as text.

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

The mode pays nothing itself. `fergie_service` only records a match played to the
end (a `GameSession` of type `fergie_time`, not before `MIN_SECONDS`), so the tasks
(`played:game:fergie_time`) and the «Путь дебютанта» can count it. The score isn't
sent: the server can't check it, so no task may depend on a win.

Rewards from the match itself and tasks on the result need agreed numbers in
`GameConfig`, the counter pairs on `User` with a migration, and the server replay in V8.
