"""The moves of «Атака 1 на 1» -> out/one-on-one-moves.glb.

    python build_moves.py

Mounts: the Mixamo "Soccer" pack at /pack (its Ch38_nonPBR.fbx is the rig
of public/career-3d/footballer.glb, so its clips need no retargeting), this
folder at /work. Docker: see tools/free-kick-3d/README.md (same image,
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
import os
import re

import bpy
from mathutils import Matrix

src, out = '/pack', '/work/out'
os.makedirs(out, exist_ok=True)

# Our clip -> (pack file, mirrored?).
CLIPS = {
    # The attacker.
    'shot_r': ('strike foward jog', False),
    'shot_l': ('strike foward jog', True),
    # Struck with everything: the full swing off a run-up.
    'power_r': ('soccer penalty kick', False),
    'power_l': ('soccer penalty kick', True),
    'pass_r': ('kick soccerball (2)', False),
    'pass_l': ('kick soccerball', False),
    'chip_l': ('kick up soccerball', False),
    'chip_r': ('kick up soccerball', True),
    'strafe_l': ('jog strafe left', False),
    'strafe_r': ('jog strafe right', False),
    'trip': ('soccer trip', False),
    # The keeper.
    'gk_scoop': ('goalkeeper scoop', False),
    'gk_catch_high': ('goalkeeper catch (4)', False),
    'gk_catch_low': ('goalkeeper catch', False),
    'gk_block_l': ('goalkeeper body block', False),
    'gk_block_r': ('goalkeeper body block (2)', False),
    'gk_miss': ('goalkeeper miss', False),
    'gk_getup': ('standing up', False),
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

arm.animation_data.action = None
bpy.ops.export_scene.gltf(
    filepath=f'{out}/one-on-one-moves.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_morph=False, export_def_bones=True,
)
print('SIZE', os.path.getsize(f'{out}/one-on-one-moves.glb') // 1024, 'KB')
