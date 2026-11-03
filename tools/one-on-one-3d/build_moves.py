"""The moves of «Атака 1 на 1» -> out/one-on-one-moves.glb.

    python build_moves.py

Mounts: the Mixamo "Soccer" pack at /pack (its Ch38_nonPBR.fbx is the rig
of public/career-3d/footballer.glb, so its clips need no retargeting), this
folder at /work, and Anderson Rohr's «Free mocap pack 05: Soccer»
(mocap/Rokoko_Default) at /mocap: its strikes, celebrations and the
keeper's set stance are real mocap, retargeted by retarget_rokoko.py (a
source "rk:<take>:<first>:<last>" — frames of the 60 fps take). Docker: see tools/free-kick-3d/README.md (same image,
`pip install bpy`).

Only the skeleton and the clips go out (no mesh); the scene plays them on
footballer.glb's model by bone name. The pack's kicks are mostly right
footed: the left ones are the same clips mirrored (Blender's flipped pose
paste, frame by frame). Then, with Node (gltf-transform 4.1.1):
tools/career-replay-3d/strip_moves.mjs drops fingers, scale channels and the
rig's empty take, and `gltf-transform optimize ... --compress meshopt
--simplify false --join false --flatten false` gives
public/one-on-one-3d/moves.glb. inspect_pack.py prints what each clip of the
pack does (foot, contact frame, travel).
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

# Our clip -> (pack file, mirrored?).
CLIPS = {
    # The attacker.
    'shot_r': ('strike foward jog', False),
    'shot_l': ('strike foward jog', True),
    # Struck with everything: the full swing off a run-up (mocap: a real
    # left foot, not the right one mirrored).
    'power_r': ('rk:10_Penalty_Kick_01:360:444', False),
    'power_l': ('rk:09_Power_Kick:120:205', False),
    # Side-footed: the inside of the foot through the ball.
    'pass_r': ('rk:08_Side_Foot_Kick:45:135', False),
    'pass_l': ('rk:08_Side_Foot_Kick:45:135', True),
    'chip_l': ('kick up soccerball', False),
    'chip_r': ('kick up soccerball', True),
    'strafe_l': ('jog strafe left', False),
    'strafe_r': ('jog strafe right', False),
    'trip': ('soccer trip', False),
    # Goal celebrations: down on his knees, arms up on the run, the leap.
    'cheer_knees': ('rk:12_Goal_Celebration_01:1:210', False),
    'cheer_arms': ('rk:13_Goal_Celebration_02:1:213', False),
    'cheer_leap': ('rk:14_Goal_Celebration_03:1:192', False),
    # The keeper.
    'gk_scoop': ('goalkeeper scoop', False),
    'gk_catch_high': ('goalkeeper catch (4)', False),
    'gk_catch_low': ('goalkeeper catch', False),
    'gk_block_l': ('goalkeeper body block', False),
    'gk_block_r': ('goalkeeper body block (2)', False),
    'gk_miss': ('goalkeeper miss', False),
    'gk_getup': ('standing up', False),
    # Set, on his toes, as the attacker comes in (looped there and back).
    'gk_set': ('rk:15_Goalkeeper_Save_01:60:280:pingpong', False),
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
    for f, mats in frames:
        for pb in order:
            pb.matrix = MIRROR @ mats[twin(pb.name)] @ MIRROR @ fix[pb.name]
            bpy.context.view_layer.update()
        for pb in order:
            pb.keyframe_insert('location', frame=f, group=pb.name)
            pb.keyframe_insert('rotation_quaternion', frame=f, group=pb.name)
    arm.animation_data.action = None
    return new


for clip, (fname, flip) in CLIPS.items():
    act = load(fname)
    if flip:
        act = mirrored(act, clip)
    else:
        act.name = clip
    act.use_fake_user = True
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, int(act.frame_range[0]), act)
    track.mute = True
    print('CLIP', clip, tuple(act.frame_range), 'mirrored' if flip else '')



# --- Composed moves: keyed from poses of the pack's clips -------------------
# (frame of ours at 30 fps, [(pack clip, its frame, weight), ...], body
# turned about the vertical (deg, + to his left)).
ROULETTE = [
    (1, [('jog forward', 10, 1)], 0),
    # The right sole on the ball...
    (5, [('stall soccerball (2)', 16, 1)], -25),
    # ...rolling it back as he pivots on the left, his back to the defender...
    (9, [('stall soccerball (2)', 22, 0.5), ('offensive idle', 1, 0.5)], -110),
    (12, [('offensive idle', 1, 1)], -180),
    # ...the left sole takes it on round...
    (16, [('stall soccerball', 16, 1)], -255),
    (19, [('stall soccerball', 22, 0.5), ('offensive idle', 1, 0.5)], -320),
    # ...and away.
    (22, [('jog forward', 10, 1)], -360),
]
COMPOSED = {'roulette_r': (ROULETTE, False), 'roulette_l': (ROULETTE, True)}


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


def composed(name, keys):
    sources = {}
    for _, parts, _ in keys:
        for clip, _, _ in parts:
            if clip not in sources:
                sources[clip] = load(clip)
                sources[clip].name = '_src_' + clip
    # The vertical in the rig's own (armature) space.
    w = arm.matrix_world.to_3x3().normalized()
    up = (w.inverted() @ Vector((0, 0, 1))).normalized()
    hips = arm.pose.bones[prefix + 'Hips']
    # First every key's pose, with no action on the rig (an action would
    # override the pose on each update)...
    posed = []
    for frame, parts, turn in keys:
        pose = mixed([(pose_of(sources[c], f), wt) for c, f, wt in parts])
        arm.animation_data.action = None
        for pb in arm.pose.bones:
            q, loc = pose[pb.name]
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = q
            pb.location = loc
        bpy.context.view_layer.update()
        # On the spot (the scene moves him): only the height of the hips.
        m = hips.matrix.copy()
        rest = hips.bone.matrix_local.translation
        m.translation = rest - up * rest.dot(up) + up * m.translation.dot(up)
        hips.matrix = Matrix.Rotation(math.radians(turn), 4, up) @ m
        bpy.context.view_layer.update()
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
    act.use_fake_user = True
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, int(act.frame_range[0]), act)
    track.mute = True
    print('CLIP', clip, tuple(act.frame_range), 'composed', 'mirrored' if flip else '')

arm.animation_data.action = None
# A mirrored clip's source (a second copy of a take) would go out too.
for act in list(bpy.data.actions):
    if act.name not in CLIPS and act.name not in COMPOSED:
        bpy.data.actions.remove(act)
bpy.ops.export_scene.gltf(
    filepath=f'{out}/one-on-one-moves.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_morph=False, export_def_bones=True,
)
print('SIZE', os.path.getsize(f'{out}/one-on-one-moves.glb') // 1024, 'KB')
