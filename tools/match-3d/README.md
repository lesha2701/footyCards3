# 11-a-side 3D match: extra moves

`frontend/public/match-3d/moves.glb` (454 KB, 28 clips, 36.3 s): skeleton and
clips only, played by bone name on `public/career-3d/footballer.glb`, like
`public/one-on-one-3d/moves.glb`. Neither source pack is in the repo.

- `build_moves.py`: the clips -> `out/moves-raw.glb`; its `REPORT` lines give
  what each clip does (travel, hips turn, foot and hand peaks, seams).
- `retarget_rokoko.py`: copy of the one-on-one tool's mocap retargeting.
- `inspect_takes.py`, `scan_takes.py`: timelines of the sources; loop windows,
  lean-back and hands-to-head poses. They chose the frames in `build_moves.py`.
- `verify_moves.mjs`: the finished file against footballer.glb and the older
  moves: bone names, no fingers, no scale, no duplicate clip, biggest step.
- `package.json`: the toolchain. Keep the `overrides`. Without them `cli@4.1.1`
  pulls `functions`/`extensions` 4.5.x and a second `core`: optimize then either
  stops with `document.hasExtension is not a function` or, worse, silently skips
  pruning and quantisation (1.29 MB instead of 454 KB).

## Rebuild

From the repo root in Git Bash, with `<pack>` the Mixamo "Soccer Game Pack" and
`<mocap>` the mocap pack's `mocap/Rokoko_Default`. The image is any Python 3.11
with `pip install bpy` (5.0.1 here; see tools/free-kick-3d/README.md for its apt
packages).

```bash
export MSYS_NO_PATHCONV=1
W="$(cd tools/match-3d && pwd -W)"; S="$(cd tools/career-replay-3d && pwd -W)"
O="$(cd frontend/public/match-3d && pwd -W)"
mkdir -p tools/match-3d/out/ref
cp frontend/public/career-3d/footballer.glb tools/match-3d/out/ref/
cp frontend/public/one-on-one-3d/moves.glb tools/match-3d/out/ref/one-on-one-moves.glb

# 1. Blender: -> out/moves-raw.glb, out/build.log (several minutes)
docker run -d --name fc-bpy-match3d -v "<pack>:/pack:ro" -v "<mocap>:/mocap:ro" -v "$W:/work" <bpy image> sleep infinity
docker exec fc-bpy-match3d sh -c 'cd /work && python build_moves.py > out/build.log 2>&1'

# 2. Node: strip, compress, verify
docker run -d --name fc-gltf-match3d -v "$W:/work" -v "$S:/strip:ro" -v "$O:/dist" node:20-alpine sleep infinity
docker exec fc-gltf-match3d sh -c 'mkdir -p /opt/gt && cd /opt/gt \
  && cp /work/package.json /work/verify_moves.mjs /strip/strip_moves.mjs . && npm install --no-audit --no-fund \
  && node strip_moves.mjs /work/out/moves-raw.glb /work/out/moves-stripped.glb \
  && npx --no-install gltf-transform optimize /work/out/moves-stripped.glb /dist/moves.glb \
       --compress meshopt --simplify false --join false --flatten false \
  && node verify_moves.mjs /dist/moves.glb /work/out/ref/footballer.glb /work/out/ref/one-on-one-moves.glb'
```

## Conventions

- Keys are at 30 fps and clips start at t=0 (the older moves files start at
  1/30 s).
- All are in-place clips. The hips keep their horizontal travel so a loop's
  natural speed can be read from the track; the game drops it at load.
- He faces forward (+z in the game); "left" below is his own left.
- `dragback` ends with the hips turned 180 degrees: the game must flip his
  heading when it ends. `fall_side` ends on the ground and `getup_front` starts
  from that same pose.

## Clips

Times in seconds. Positions in metres, relative to the hips.

| clip | s | kind | key times and notes |
|---|---|---|---|
| dribble_jog | 0.97 | loop | 1.13 m/s; pelvis swings -9..+20 deg; foot peaks L 0.07, R 0.47 |
| dribble_run | 0.57 | loop | 1.56 m/s; foot peaks L 0.10, R 0.40 |
| jockey | 0.97 | loop | low stance backing off, 0.19 m/s, hips turned about +19 deg |
| jockey_l | 0.60 | loop | real shuffle, diagonal: 0.37 m/s left and 0.35 m/s back |
| jockey_r | 0.60 | loop | jockey_l mirrored |
| tackle_r, tackle_l | 1.00 | one-off | poke 0.27, toe 0.19 out and 0.32 ahead; hips turn up to 42 deg |
| trap_r | 0.53 | one-off | sole on ball 0.27-0.33; ankle 0.22 to his right, 0.49 ahead |
| trap_l | 0.53 | one-off | sole on ball 0.27-0.33; ankle 0.15 to his left, 0.40 ahead |
| chest_trap | 1.40 | one-off | chest about 0.65, ball down to the right foot after the clip |
| stepover_r | 0.67 | one-off | foot over ball 0.23 (ball about 0.40 ahead), plants 0.43 with sway -30 deg, net turn 0; ball to his left about 0.55 |
| stepover_l | 0.67 | one-off | mirrored: sway +30 deg, ball to his right |
| dragback | 0.70 | one-off | right sole on ball 0.23-0.47, pulled back about 0.35; turns 180 deg to his right |
| ballroll_r | 0.60 | one-off | right sole rolls ball 0.23-0.43, about 0.34 across to his left; net turn 0 |
| ballroll_l | 0.60 | one-off | mirrored, ball to his right |
| throw_in | 1.67 | one-off | starts ball overhead, backswing 0.53, release about 0.68 |
| penalty | 1.50 | one-off | starts mid run-up, contact 0.73, toe 0.39 to his right of the hips |
| gk_throw | 2.50 | one-off | overhand, release about 1.53 |
| gk_roll | 2.97 | one-off | release 1.13, hand 0.26 off the ground |
| gk_dropkick | 3.70 | one-off | contact 2.10 |
| gk_sidestep_l | 0.53 | loop | 2.11 m/s to his left |
| gk_sidestep_r | 0.50 | loop | 2.81 m/s to his right |
| gk_directing | 2.60 | one-off | right arm up about 0.4, both arms up about 1.6-2.4; he walks in the source |
| gk_save_high | 2.00 | one-off | leap to his left, hands top about 0.65, apex about 0.75 |
| gk_save_low | 2.90 | one-off | scoop, hands low about 1.2, stands up by the end |
| fall_side | 1.00 | one-off | taken off his feet, lands on his side about 0.9 |
| getup_front | 1.30 | one-off | from fall_side's end: over his back, all fours, up |
| dejected | 1.77 | one-off | hands on head 0.37-1.30, back to standing |
