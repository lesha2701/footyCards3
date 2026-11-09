"""The extra moves of the 11-a-side 3D match -> out/moves-raw.glb.

    python build_moves.py

Follows tools/one-on-one-3d/build_moves.py (copied, not imported: that tool
has its own clip list). Mounts: the Mixamo "Soccer" pack at /pack (its
Ch38_nonPBR.fbx is the rig of public/career-3d/footballer.glb), the Rokoko
takes of «Free mocap pack 05: Soccer» at /mocap, this folder at /work. See
README.md for the commands and what each clip is.

Only the skeleton and the clips go out; the game plays them on footballer.glb
by bone name. New here:
- every clip is baked (`bake`): rotations of all bones but the fingers, the
  location of the hips only. The hips start over the origin and keep their
  travel, so a loop's natural speed can be read off the track as for `run`;
  the game drops the horizontal part at load.
- `forward`: the takes run in any direction, so the clip is turned until its
  travel is the model's forward. `turn`: a fixed turn, degrees to his left.
- `loop`: the last key is made equal to the first, the difference spread over
  the cycle (the frames were picked by scan_takes.py, so it is small).
- `frames`: a part of a pack clip.
- composed moves can place the ankles (two-bone IK), lean and bow the body.
"""
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, '/work')
from retarget_rokoko import rokoko_action  # noqa: E402

src, out = '/pack', '/work/out'
os.makedirs(out, exist_ok=True)

# Our clip -> (source, mirrored?, options). Sources: a pack file, or
# "rk:<take>:<first>:<last>" (frames of the 60 fps take).
CLIPS = {
    # With the ball at his feet: real cycles of the dribble takes.
    'dribble_jog': ('rk:03_Dribble_03:99:157', False, {'loop': True, 'forward': True, 'turn': -15}),
    # (237-275 scores better at the seam but weaves, feet 0.45 m out each side.)
    'dribble_run': ('rk:01_Dribble_01:16:50', False, {'loop': True, 'forward': True}),
    # Low, backing off; the shuffle to his left is real, the right mirrored.
    'jockey': ('rk:18_Defending_01:136:194', False, {'loop': True}),
    'jockey_l': ('rk:19_Defending_02:46:82', False, {'loop': True}),
    'jockey_r': ('rk:19_Defending_02:46:82', True, {'loop': True}),
    # The lunge that ends the defending take (the pack's tackles all go to
    # ground: (2) is a slide, (3) a tumble).
    'tackle_r': ('rk:19_Defending_02:427:487', False, {}),
    'tackle_l': ('rk:19_Defending_02:427:487', True, {}),
    # Arms out, leans back, the ball off the chest and down to the foot.
    'chest_trap': ('rk:05_Juggling_02:427:511', False, {}),
    # From the ball held overhead: the backswing, the throw, the arms down.
    'throw_in': ('rk:07_Throw_In:356:456', False, {}),
    # A placed kick, not power_r's full swing.
    'penalty': ('soccer penalty kick', False, {'forward': True}),
    # The keeper with the ball.
    'gk_throw': ('goalkeeper overhand throw', False, {'frames': (1, 76)}),
    'gk_roll': ('goalkeeper pass', False, {'frames': (1, 90)}),
    'gk_dropkick': ('goalkeeper drop kick', False, {'frames': (1, 112)}),
    'gk_sidestep_l': ('goalkeeper sidestep', False, {}),
    'gk_sidestep_r': ('goalkeeper sidestep (2)', False, {}),
    'gk_directing': ('goalkeeper directing (2)', False, {'frames': (76, 154)}),
    # The mocap keeper never goes to ground: a leap to his left, a scoop.
    'gk_save_high': ('rk:15_Goalkeeper_Save_01:277:397', False, {'turn': -20}),
    'gk_save_low': ('rk:17_Goalkeeper_Save_03:361:535', False, {}),
    # The real slide: feet first on his hip, the leading foot 0.93 m ahead, a hand
    # on the grass, and up from it. (`soccer tackle`, the one-on-one's slide_*, is
    # a dive on to his front.)
    'slide_tackle_r': ('soccer tackle (2)', False, {}),
    'slide_tackle_l': ('soccer tackle (2)', True, {}),
    # Taken off his feet, then up: one clip of the pack cut in two, so the
    # second starts where the first ends (on his side).
    'fall_side': ('soccer tackle (3)', False, {'frames': (1, 31)}),
    'getup_front': ('soccer tackle (3)', False, {'frames': (31, 70)}),
}
FINGERS = re.compile(r'Hand(Thumb|Index|Middle|Ring|Pinky)\d')


def fcurves(act):
    # Blender 5: actions are layered.
    if len(getattr(act, 'fcurves', [])) > 0:
        return list(act.fcurves)
    return [fc for layer in act.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f'{src}/Ch38_nonPBR.fbx')
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
arm.name = 'Footballer'
for o in list(bpy.data.objects):
    if o.type == 'MESH':
        bpy.data.objects.remove(o, do_unlink=True)
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action = None
prefix = next(b.name for b in arm.data.bones if b.name.endswith('Hips'))[:-len('Hips')]
arm.animation_data_create()
scene = bpy.context.scene
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

hips = arm.pose.bones[prefix + 'Hips']
# The field in the rig's own (armature) space: he faces -Y, his left is +X.
world = arm.matrix_world.to_3x3().normalized()
UP = (world.inverted() @ Vector((0, 0, 1))).normalized()
LEFT = (world.inverted() @ Vector((1, 0, 0))).normalized()
FWD = (world.inverted() @ Vector((0, -1, 0))).normalized()
UNITS = 1 / arm.matrix_world.to_scale().x  # armature units in a metre


def load(fname):
    """The pack file's action, its channels on our rig's bone names."""
    if fname.startswith('rk:'):
        _, take, f0, f1, *opt = fname.split(':')
        act = rokoko_action(arm, prefix, take, int(f0), int(f1), pingpong='pingpong' in opt)
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        return act
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f'{src}/{fname}.fbx')
    new = [o for o in bpy.data.objects if o not in before]
    act = [o for o in new if o.type == 'ARMATURE'][0].animation_data.action
    for fc in fcurves(act):
        fc.data_path = re.sub(r'mixamorig\d*:', prefix, fc.data_path)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    return act


MIRROR = Matrix.Scale(-1, 4, (1, 0, 0))


def twin(name):
    return name.replace('Left', '\0').replace('Right', 'Left').replace('\0', 'Right')


def parents_first(bones):
    done, order = set(), []
    while len(order) < len(bones):
        for pb in bones:
            if pb.name not in done and (pb.parent is None or pb.parent.name in done):
                done.add(pb.name)
                order.append(pb)
    return order


def mirrored(act, name):
    """The action played left for right: every bone takes its twin's pose
    mirrored across the body (armature space). The constant `fix` turns the
    mirrored twin's rest frame into this bone's own, whatever the rig's
    bone rolls are."""
    f0, f1 = (int(x) for x in act.frame_range)
    bones = [pb for pb in arm.pose.bones if not FINGERS.search(pb.name)]
    rest = {pb.name: pb.bone.matrix_local for pb in arm.pose.bones}
    fix = {pb.name: (MIRROR @ rest[twin(pb.name)] @ MIRROR).inverted() @ rest[pb.name] for pb in bones}
    arm.animation_data.action = act
    frames = []
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        frames.append((f, {pb.name: pb.matrix.copy() for pb in arm.pose.bones}))
    new = bpy.data.actions.new(name)
    arm.animation_data.action = new
    order = parents_first(bones)
    last = {}
    for f, mats in frames:
        for pb in order:
            pb.matrix = MIRROR @ mats[twin(pb.name)] @ MIRROR @ fix[pb.name]
            bpy.context.view_layer.update()
        for pb in order:
            q = pb.rotation_quaternion.copy()
            if pb.name in last and last[pb.name].dot(q) < 0:
                q.negate()
            last[pb.name] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert('rotation_quaternion', frame=f, group=pb.name)
            if pb == hips:
                pb.keyframe_insert('location', frame=f, group=pb.name)
    arm.animation_data.action = None
    return new


def horizontal(v):
    return v - UP * v.dot(UP)


def degrees_between(a, b):
    return 2 * math.degrees(math.acos(min(1, abs(a.normalized().dot(b.normalized())))))


def bake(act, name, frames=None, loop=False, forward=False, turn=0.0):
    """The action as our clip: see the module's docstring."""
    f0, f1 = (int(x) for x in act.frame_range)
    if frames:
        f0, f1 = frames
    bones = [pb for pb in arm.pose.bones if not FINGERS.search(pb.name)]
    arm.animation_data.action = act
    poses, track = [], []
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        poses.append({pb.name: [pb.rotation_quaternion.copy(), pb.location.copy()] for pb in bones})
        track.append(hips.matrix.translation.copy())
    n = len(poses) - 1
    travel = horizontal(track[-1] - track[0])
    line = math.atan2(travel.cross(FWD).dot(UP), travel.dot(FWD)) if forward else 0.0
    angle = line + math.radians(turn)
    for pb in bones:
        last = None
        for p in poses:
            if last is not None and last.dot(p[pb.name][0]) < 0:
                p[pb.name][0].negate()
            last = p[pb.name][0]
    if loop:
        gaps = sorted(((degrees_between(poses[0][pb.name][0], poses[-1][pb.name][0]), pb.name[len(prefix):]) for pb in bones), reverse=True)
        print(f'SEAM {name}: before closing', ', '.join(f'{b} {d:.0f}' for d, b in gaps[:4]), flush=True)
        for pb in bones:
            dq = [a - b for a, b in zip(poses[-1][pb.name][0], poses[0][pb.name][0])]
            dl = poses[-1][pb.name][1] - poses[0][pb.name][1]
            for i, p in enumerate(poses):
                q = p[pb.name][0]
                for c in range(4):
                    q[c] -= dq[c] * i / n
                q.normalize()
                p[pb.name][1] = p[pb.name][1] - dl * (i / n)
    # The hips: with no action on the rig (it would override the pose).
    arm.animation_data.action = None
    spin = Matrix.Rotation(angle, 4, UP)
    rest = horizontal(hips.bone.matrix_local.translation)
    base = None
    last = None
    for i, p in enumerate(poses):
        hips.rotation_quaternion, hips.location = p[hips.name]
        bpy.context.view_layer.update()
        m = hips.matrix.copy()
        t = m.translation.copy()
        base = horizontal(t) if base is None else base
        way = horizontal(t) - base + (travel * (i / n) if loop else Vector((0, 0, 0)))
        m = spin @ m
        # `turn` turns the body, not the way it goes.
        m.translation = rest + (Matrix.Rotation(line, 3, UP) @ way) + UP * t.dot(UP)
        hips.matrix = m
        bpy.context.view_layer.update()
        q = hips.rotation_quaternion.copy()
        if last is not None and last.dot(q) < 0:
            q.negate()
        last = q
        p[hips.name] = [q, hips.location.copy()]
    new = bpy.data.actions.new(name)
    arm.animation_data.action = new
    for i, p in enumerate(poses):
        for pb in bones:
            pb.rotation_quaternion = p[pb.name][0]
            pb.keyframe_insert('rotation_quaternion', frame=i + 1, group=pb.name)
        hips.location = p[hips.name][1]
        hips.keyframe_insert('location', frame=i + 1, group=hips.name)
    arm.animation_data.action = None
    return new


def finish(clip, act, note=''):
    act.name = clip
    act.use_fake_user = True
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, int(act.frame_range[0]), act)
    track.mute = True
    print('CLIP', clip, tuple(act.frame_range), note, flush=True)


for clip, (fname, flip, opts) in CLIPS.items():
    act = bake(load(fname), clip + '_src' if flip else clip, **opts)
    if flip:
        act = mirrored(act, clip)
    finish(clip, act, 'mirrored' if flip else '')


# --- Composed moves ----------------------------------------------------------
# (frame of ours at 30 fps, [(source, its frame, weight), ...], body turned
# about the vertical (deg, + to his left), options). Options: `lean` (deg, +
# to his left), `bow` (deg, + forward, spine and neck), `h` (the hips, metres
# up), `R` / `L`: the ankle at (left, forward, up) metres on the field, the
# hips being over the origin; a fourth item 'flat' lays the foot on the grass.
G = 0.12  # the ankle's height with the foot on the grass
RUN = [('jog forward', 10, 1)]  # right foot 0.4 m behind him, left under him
RUN2 = [('jog forward', 22, 1)]  # the other way about
THROUGH = [('jog forward', 16, 1)]  # right foot coming through, left behind him
LIFT = 'stall soccerball (2)'  # his right foot comes up, stands on the ball
PLANT = (0.11, 0.05, G, 'flat')
# Right foot over the ball from its inside to its outside, his weight goes
# after it, then the push off that foot and away to his left.
STEPOVER = [
    (1, THROUGH, 0),
    (5, [(LIFT, 7, 1)], -6, dict(lean=6, h=-0.02, R=(0.06, 0.30, 0.20), L=PLANT)),
    (8, [(LIFT, 13, 1)], -4, dict(lean=4, h=-0.02, R=(0.02, 0.42, 0.34), L=PLANT)),
    (11, [(LIFT, 13, 0.5), ('jog strafe right', 6, 0.5)], -18, dict(lean=-6, h=-0.03, R=(-0.20, 0.40, 0.30), L=PLANT)),
    (14, [('jog strafe right', 6, 1)], -30, dict(lean=-14, h=-0.05, R=(-0.36, 0.22, G + 0.01, 'flat'), L=(0.12, 0.05, G + 0.02))),
    (17, [('jog strafe left', 6, 1)], -5, dict(lean=-4, h=-0.03, R=(-0.30, 0.05, G + 0.04), L=(0.22, 0.25, G + 0.01))),
    (21, RUN, 0),
]
# The right sole comes onto the ball and pulls it back past the standing
# foot while he pivots on that foot, round to his right.
DRAGBACK = [
    (1, THROUGH, 0),
    (5, [(LIFT, 10, 1)], -4, dict(h=-0.02, R=(-0.10, 0.30, 0.24), L=PLANT)),
    (8, [(LIFT, 16, 1)], -8, dict(lean=2, h=-0.03, R=(-0.10, 0.42, 0.35), L=PLANT)),
    (12, [(LIFT, 22, 1)], -30, dict(h=-0.04, R=(-0.12, 0.20, 0.35), L=PLANT)),
    (15, [(LIFT, 22, 0.5), ('offensive idle', 1, 0.5)], -80, dict(h=-0.04, R=(-0.16, 0.04, 0.33), L=PLANT)),
    (18, [('offensive idle', 1, 1)], -135, dict(h=-0.03, R=(-0.24, -0.16, G + 0.06), L=PLANT[:2] + (G + 0.01,))),
    (20, [('offensive idle', 1, 0.5), RUN2[0]], -160),
    (22, RUN2, -180),
]
# The right sole rolls the ball across his body to the left, the foot comes
# down beyond it and the left steps round behind.
BALLROLL = [
    (1, THROUGH, 0),
    (5, [(LIFT, 10, 1)], -4, dict(lean=3, h=-0.02, R=(-0.12, 0.32, 0.26), L=PLANT)),
    (8, [(LIFT, 16, 1)], 0, dict(lean=4, h=-0.03, R=(-0.10, 0.36, 0.35), L=PLANT)),
    (11, [(LIFT, 19, 1)], 6, dict(lean=6, h=-0.03, R=(0.08, 0.34, 0.35), L=PLANT)),
    (14, [(LIFT, 22, 0.5), ('jog strafe left', 6, 0.5)], 14, dict(lean=10, h=-0.03, R=(0.24, 0.30, 0.30), L=PLANT)),
    (16, [('jog strafe left', 6, 1)], 18, dict(lean=10, h=-0.03, R=(0.28, 0.16, G + 0.01, 'flat'), L=(0.24, -0.14, G + 0.08))),
    (19, RUN2, 0),
]
# First touch of a ground ball: the foot up on it, and back. The pack's stall
# at about twice its speed, without its flick.
# The pack's foot stands on a ball higher than ours: the ankle is put at the
# top of a ball on the grass.
TOUCH = [(1, 1), (3, 4), (5, 7), (7, 10), (9, 13), (11, 16), (14, 8), (17, 1)]
BALL_TOP = 0.34


def touch(clip, key, left, fwd):
    return [(ours, [(clip, theirs, 1)], 0, {key: (left, fwd, BALL_TOP)} if ours in (9, 11) else {}) for ours, theirs in TOUCH]


TRAP_R = touch('stall soccerball (2)', 'R', -0.22, 0.50)
TRAP_L = touch('stall soccerball', 'L', 0.16, 0.42)
# Hands on his head: the arms of the throw-in's backswing (frame 3 here is
# 388 of the take), the arch of that backswing bowed away, feet together.
STAND = [('transition', 1, 1)]
HANDS = 'rk:07_Throw_In:384:392'
DOWN = dict(h=0.05, R=(-0.11, 0.0, G, 'flat'), L=(0.11, 0.0, G, 'flat'))
DEJECTED = [
    (1, STAND, 0),
    (12, [(HANDS, 3, 1)], 0, dict(DOWN, bow=20)),
    (26, [(HANDS, 3, 1)], 0, dict(DOWN, bow=28)),
    (40, [(HANDS, 3, 1)], 0, dict(DOWN, bow=22)),
    (54, STAND, 0),
]
COMPOSED = {
    'trap_r': (TRAP_R, False),
    'trap_l': (TRAP_L, False),
    'stepover_r': (STEPOVER, False),
    'stepover_l': (STEPOVER, True),
    'dragback': (DRAGBACK, False),
    'ballroll_r': (BALLROLL, False),
    'ballroll_l': (BALLROLL, True),
    'dejected': (DEJECTED, False),
}


def pose_of(act, frame):
    """Each bone's local rotation and location at that frame of the action."""
    arm.animation_data.action = act
    scene.frame_set(frame)
    return {pb.name: (pb.rotation_quaternion.copy(), pb.location.copy()) for pb in arm.pose.bones}


def mixed(poses):
    """A weighted mix of poses (slerped one into the next)."""
    out, total = {}, 0.0
    for pose, w in poses:
        total += w
        for name, (q, loc) in pose.items():
            if name not in out:
                out[name] = (q.copy(), loc.copy())
            else:
                q0, l0 = out[name]
                out[name] = (q0.slerp(q, w / total), l0.lerp(loc, w / total))
    return out


def about(pb, axis, deg):
    """The bone turned about its own head (armature space)."""
    at = pb.matrix.translation.copy()
    m = Matrix.Rotation(math.radians(deg), 4, axis) @ pb.matrix
    m.translation = at
    pb.matrix = m
    bpy.context.view_layer.update()


def turn_to(pb, have, want):
    """The bone turned about its head so the vector `have` becomes `want`."""
    at = pb.matrix.translation.copy()
    m = have.rotation_difference(want).to_matrix().to_4x4() @ pb.matrix
    m.translation = at
    pb.matrix = m
    bpy.context.view_layer.update()


def place_ankle(side, spec, turn):
    """Two-bone IK: the ankle at the field position `spec`, the knee staying
    on the side it bends to, the foot keeping its orientation (or flat)."""
    thigh = arm.pose.bones[prefix + side + 'UpLeg']
    shin = arm.pose.bones[prefix + side + 'Leg']
    foot = arm.pose.bones[prefix + side + 'Foot']
    left, fwd, up = spec[:3]
    target = (LEFT * left + FWD * fwd + UP * up) * UNITS
    keep = foot.matrix.to_3x3()
    if 'flat' in spec[3:]:
        keep = Matrix.Rotation(math.radians(turn), 3, UP) @ foot.bone.matrix_local.to_3x3()
    h = thigh.matrix.translation.copy()
    k = shin.matrix.translation.copy()
    a = foot.matrix.translation.copy()
    la, lb = (k - h).length, (a - k).length
    aim = target - h
    d = min(aim.length, (la + lb) * 0.995)
    aim.normalize()
    pole = (k - h) - aim * (k - h).dot(aim)
    if pole.length < 1e-3 * la:
        pole = Matrix.Rotation(math.radians(turn), 3, UP) @ FWD
    pole.normalize()
    along = (la * la - lb * lb + d * d) / (2 * d)
    knee = h + aim * along + pole * math.sqrt(max(la * la - along * along, 0))
    turn_to(thigh, k - h, knee - h)
    k = shin.matrix.translation.copy()
    a = foot.matrix.translation.copy()
    turn_to(shin, a - k, h + aim * d - k)
    m = keep.to_4x4()
    m.translation = foot.matrix.translation
    foot.matrix = m
    bpy.context.view_layer.update()


def composed(name, keys):
    sources = {}
    for _, parts, *_ in keys:
        for clip, _, _ in parts:
            if clip not in sources:
                sources[clip] = load(clip)
                sources[clip].name = '_src_' + clip
    # First every key's pose, with no action on the rig (an action would
    # override the pose on each update)...
    posed = []
    for frame, parts, turn, *more in keys:
        opts = more[0] if more else {}
        pose = mixed([(pose_of(sources[c], f), wt) for c, f, wt in parts])
        arm.animation_data.action = None
        for pb in arm.pose.bones:
            q, loc = pose[pb.name]
            pb.rotation_quaternion = q
            pb.location = loc
        bpy.context.view_layer.update()
        # On the spot (the scene moves him): only the height of the hips.
        m = hips.matrix.copy()
        rest = hips.bone.matrix_local.translation
        at = horizontal(rest) + UP * (m.translation.dot(UP) + opts.get('h', 0) * UNITS)
        # Lean about the forward axis (+ to his left), then the turn.
        m = Matrix.Rotation(math.radians(turn), 4, UP) @ Matrix.Rotation(math.radians(opts.get('lean', 0)), 4, -FWD) @ m
        m.translation = at
        hips.matrix = m
        bpy.context.view_layer.update()
        if 'bow' in opts:
            side = Matrix.Rotation(math.radians(turn), 3, UP) @ LEFT
            about(arm.pose.bones[prefix + 'Spine1'], side, opts['bow'] / 2)
            about(arm.pose.bones[prefix + 'Neck'], side, opts['bow'] / 2)
        for side, key in (('Right', 'R'), ('Left', 'L')):
            if key in opts:
                place_ankle(side, opts[key], turn)
        posed.append((frame, {pb.name: (pb.rotation_quaternion.copy(), pb.location.copy()) for pb in arm.pose.bones}))
    # ...then the keys.
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    last = {}
    for frame, pose in posed:
        for pb in arm.pose.bones:
            if FINGERS.search(pb.name):
                continue
            q, loc = pose[pb.name]
            # Keys interpolate component-wise: stay on one side of the sphere.
            if pb.name in last and last[pb.name].dot(q) < 0:
                q.negate()
            last[pb.name] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert('rotation_quaternion', frame=frame, group=pb.name)
            if pb == hips:
                pb.location = loc
                pb.keyframe_insert('location', frame=frame, group=pb.name)
    arm.animation_data.action = None
    return act


for clip, (keys, flip) in COMPOSED.items():
    act = composed(clip + '_src' if flip else clip, keys)
    act = mirrored(act, clip) if flip else act
    finish(clip, act, 'composed mirrored' if flip else 'composed')


# --- What each clip does ------------------------------------------------------
def on_field(pb):
    return arm.matrix_world @ pb.head


# Frames of ours where a foot is on the ball: where it is then.
ON_BALL = {'trap_r': 10, 'trap_l': 10, 'tackle_r': 9, 'tackle_l': 9, 'slide_tackle_r': 19, 'stepover_r': 8, 'dragback': 8, 'ballroll_r': 8}


def report(clip):
    act = bpy.data.actions[clip]
    f0, f1 = (int(x) for x in act.frame_range)
    arm.animation_data.action = act
    names = {'toeL': 'LeftToeBase', 'toeR': 'RightToeBase', 'footL': 'LeftFoot', 'footR': 'RightFoot',
             'handL': 'LeftHand', 'handR': 'RightHand', 'hips': 'Hips', 'upL': 'LeftUpLeg', 'upR': 'RightUpLeg'}
    bs = {k: arm.pose.bones[prefix + v] for k, v in names.items()}
    bs['head'] = arm.pose.bones[prefix + 'Head']
    rows, keys = [], []
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        rows.append({k: on_field(b).copy() for k, b in bs.items()})
        keys.append({pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones if not FINGERS.search(pb.name)})
    first, last = keys[0], keys[-1]
    yaws = []
    for r in rows:
        d = r['upL'] - r['upR']
        y = math.degrees(math.atan2(d.y, d.x))
        if yaws:
            while y - yaws[-1] > 180:
                y -= 360
            while y - yaws[-1] < -180:
                y += 360
        yaws.append(y)
    secs = (f1 - f0) / 30
    t = rows[-1]['hips'] - rows[0]['hips']
    speed = math.hypot(t.x, t.y) / secs if secs else 0
    seam = max(degrees_between(first[k], last[k]) for k in first)
    line = (f'REPORT {clip}: {secs:.2f}s travel left {t.x:+.2f} fwd {-t.y:+.2f} ({speed:.2f} m/s); hips yaw {yaws[0]:+.0f} '
            f'min {min(yaws):+.0f} max {max(yaws):+.0f} end {yaws[-1]:+.0f}; ankle z min L {min(r["footL"].z for r in rows):.2f} '
            f'R {min(r["footR"].z for r in rows):.2f}; hips z {min(r["hips"].z for r in rows):.2f}-{max(r["hips"].z for r in rows):.2f}; '
            f'first/last differ {seam:.1f} deg')
    for k in ('toeL', 'toeR', 'handL', 'handR'):
        best, at = 0, 0
        for i in range(1, len(rows)):
            v = (rows[i][k] - rows[i - 1][k]).length * 30
            if v > best:
                best, at = v, i
        p = rows[at][k] - rows[at]['hips']
        line += f'; {k} peak {best:.1f} m/s at {at / 30:.2f}s (left {p.x:+.2f} fwd {-p.y:+.2f} z {rows[at][k].z:.2f})'
    # A loop wraps from its last-but-one key to its second (the last is the
    # first): the step there against the biggest step inside the cycle.
    step = max(max(degrees_between(a[k], b[k]) for k in a) for a, b in zip(keys, keys[1:]))
    wrap = max(degrees_between(keys[-2][k], keys[1][k]) / 2 for k in first)
    line += f'; biggest bone step {step:.1f} deg, across the wrap {wrap:.1f} deg'
    if clip == 'dejected':
        for f in (12, 26, 40):
            r = rows[f - f0]
            line += f'; at {f}: hands from head L {(r["handL"] - r["head"]).length:.2f} R {(r["handR"] - r["head"]).length:.2f}'
    if clip in ON_BALL:
        i = ON_BALL[clip] - f0
        for k in ('footL', 'footR', 'toeL', 'toeR'):
            p = rows[i][k] - rows[i]['hips']
            line += f'; at {i / 30:.2f}s {k} left {p.x:+.2f} fwd {-p.y:+.2f} z {rows[i][k].z:.2f}'
    print(line, flush=True)


for clip in list(CLIPS) + list(COMPOSED):
    report(clip)

arm.animation_data.action = None
# A mirrored clip's source, a composed move's poses would go out too.
for act in list(bpy.data.actions):
    if act.name not in CLIPS and act.name not in COMPOSED:
        bpy.data.actions.remove(act)
bpy.ops.export_scene.gltf(
    filepath=f'{out}/moves-raw.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_morph=False, export_def_bones=True,
    # A loop's first key at 0: no one-frame hold at the wrap.
    export_anim_slide_to_zero=True,
)
print('SIZE', os.path.getsize(f'{out}/moves-raw.glb') // 1024, 'KB')
