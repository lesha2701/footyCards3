"""Anderson Rohr's «Free mocap pack 05: Soccer» (Rokoko_Default rig) on our
footballer's Mixamo rig. build_moves.py takes its moves from here
(`rokoko_action`); run on its own it writes every take of CUTS (whole) to
out/rokoko-moves.glb, to look them over (and pick the parts):

    python retarget_rokoko.py [-- clip ...]

Mounts: the Mixamo "Soccer" pack at /pack (Ch38_nonPBR.fbx is the rig of
public/career-3d/footballer.glb), the pack's mocap/Rokoko_Default folder at
/mocap, this folder at /work.

Both rigs rest in a T-pose, so each mapped bone takes the source bone's
rotation away from its rest, in the world, on top of its own rest — what
the bone rolls and axes of either rig are doesn't matter. The hips also
take the source's travel, scaled by the two rigs' hip heights. Fingers
stay at rest. The 60 fps takes are sampled at 30 (Mixamo's rate).
Each CUTS entry is a take under our name (frames at 60 fps; None: all).
"""
import os
import sys

import bpy
from mathutils import Matrix

src, mocap, out = '/pack', '/mocap', '/work/out'
os.makedirs(out, exist_ok=True)

# Rokoko bone -> Mixamo bone (without the mixamorig prefix).
BONES = {
    'Hips': 'Hips',
    'Spine1': 'Spine', 'Spine2': 'Spine1', 'Spine4': 'Spine2',
    'Neck': 'Neck', 'Head': 'Head',
}
for side in ('Left', 'Right'):
    BONES.update({
        f'{side}Shoulder': f'{side}Shoulder', f'{side}Arm': f'{side}Arm',
        f'{side}ForeArm': f'{side}ForeArm', f'{side}Hand': f'{side}Hand',
        f'{side}Thigh': f'{side}UpLeg', f'{side}Shin': f'{side}Leg',
        f'{side}Foot': f'{side}Foot', f'{side}Toe': f'{side}ToeBase',
    })

# Our clip -> (take, first frame, last frame) at 60 fps; None: the whole take.
CUTS = {
    'rk_dribble_1': ('01_Dribble_01', None, None),
    'rk_dribble_2': ('02_Dribble_02', None, None),
    'rk_dribble_3': ('03_Dribble_03', None, None),
    'rk_side_foot': ('08_Side_Foot_Kick', None, None),
    'rk_power': ('09_Power_Kick', None, None),
    'rk_penalty_1': ('10_Penalty_Kick_01', None, None),
    'rk_penalty_2': ('11_Penalty_Kick_02', None, None),
    'rk_celebrate_1': ('12_Goal_Celebration_01', None, None),
    'rk_celebrate_2': ('13_Goal_Celebration_02', None, None),
    'rk_celebrate_3': ('14_Goal_Celebration_03', None, None),
    'rk_gk_save_1': ('15_Goalkeeper_Save_01', None, None),
    'rk_gk_save_2': ('16_Goalkeeper_Save_02', None, None),
    'rk_gk_save_3': ('17_Goalkeeper_Save_03', None, None),
    'rk_defend_1': ('18_Defending_01', None, None),
    'rk_defend_2': ('19_Defending_02', None, None),
}
STEP = 2  # 60 fps -> 30


def parents_first(bones):
    done, order = set(), []
    while len(order) < len(bones):
        for pb in bones:
            if pb.name not in done and (pb.parent is None or pb.parent.name in done):
                done.add(pb.name)
                order.append(pb)
    return order


def rokoko_action(arm, prefix, take, f0=None, f1=None, name=None, pingpong=False):
    """Frames f0..f1 (60 fps) of the take as an action on `arm`, keyed at
    30 fps from frame 1. `pingpong`: played on and back again, so it loops
    without a jump (a stance shifting its weight)."""
    scene = bpy.context.scene
    targets = [arm.pose.bones[prefix + m] for m in BONES.values()]
    order = parents_first(targets)
    source_of = {prefix + m: r for r, m in BONES.items()}
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    t_world = arm.matrix_world.copy()
    t_inv = t_world.inverted()
    t_rest = {pb.name: (t_world @ pb.bone.matrix_local).to_quaternion() for pb in targets}
    t_hips_h = (t_world @ arm.pose.bones[prefix + 'Hips'].bone.matrix_local).translation.z

    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f'{mocap}/{take}.fbx')
    new = [o for o in bpy.data.objects if o not in before]
    s = [o for o in new if o.type == 'ARMATURE'][0]
    act = s.animation_data.action
    a0, a1 = (int(x) for x in act.frame_range)
    f0 = a0 if f0 is None else f0
    f1 = a1 if f1 is None else f1
    s_world = s.matrix_world.copy()
    s_rest = {r: (s_world @ s.data.bones[r].matrix_local).to_quaternion() for r in BONES}
    k = t_hips_h / (s_world @ s.data.bones['Hips'].matrix_local).translation.z

    frames = list(range(f0, f1 + 1, STEP))
    if pingpong:
        frames += frames[-2:0:-1]
    out_act = bpy.data.actions.new(name or take)
    arm.animation_data.action = out_act
    for i, f in enumerate(frames):
        scene.frame_set(f)
        for pb in order:
            r = source_of[pb.name]
            sw = s_world @ s.pose.bones[r].matrix
            delta = sw.to_quaternion() @ s_rest[r].inverted()
            rot = (t_world.to_quaternion().inverted() @ (delta @ t_rest[pb.name])).to_matrix().to_4x4()
            if r == 'Hips':
                pb.matrix = Matrix.Translation((t_inv @ (sw.translation * k).to_4d()).to_3d()) @ rot
            else:
                pb.matrix = Matrix.Translation(pb.matrix.translation) @ rot
            bpy.context.view_layer.update()
        for pb in order:
            if pb.name == prefix + 'Hips':
                pb.keyframe_insert('location', frame=i + 1, group=pb.name)
            pb.keyframe_insert('rotation_quaternion', frame=i + 1, group=pb.name)
    arm.animation_data.action = None
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    # The take's own action would go out too (on bones we don't have).
    bpy.data.actions.remove(act)
    # Its import set the scene to its 60 fps: the keys are at 30.
    scene.render.fps = 30
    return out_act


if __name__ == '__main__':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=f'{src}/Ch38_nonPBR.fbx')
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
    arm.name = 'Footballer'
    for o in list(bpy.data.objects):
        if o.type == 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action = None
    arm.animation_data_create()
    prefix = next(b.name for b in arm.data.bones if b.name.endswith('Hips'))[:-len('Hips')]
    only = set(sys.argv[sys.argv.index('--') + 1:]) if '--' in sys.argv else set()
    for clip, (take, f0, f1) in CUTS.items():
        if only and clip not in only:
            continue
        act = rokoko_action(arm, prefix, take, f0, f1, clip)
        act.use_fake_user = True
        track = arm.animation_data.nla_tracks.new()
        track.name = clip
        track.strips.new(clip, 1, act)
        track.mute = True
        print('CLIP', clip, take, flush=True)
    bpy.ops.export_scene.gltf(
        filepath=f'{out}/rokoko-moves.glb', export_format='GLB',
        export_animations=True, export_animation_mode='ACTIONS',
        export_skins=True, export_yup=True, export_apply=False,
        export_morph=False, export_def_bones=True,
    )
    print('SIZE', os.path.getsize(f'{out}/rokoko-moves.glb') // 1024, 'KB')
