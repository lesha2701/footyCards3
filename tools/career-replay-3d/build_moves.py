"""Extra Mixamo clips for the 3D goal replay -> out/footballer-moves.glb.

    python build_moves.py

Mounts (see README.md): the "Soccer" pack at /pack (its Ch38_nonPBR.fbx is
the rig of public/career-3d/footballer.glb), the downloaded clips at /moves,
this folder at /work.

Only the skeleton and the clips go out (no mesh): the replay loads them next
to footballer.glb and plays them on its model by bone name. The clips were
downloaded for another auto-rigged character ('mixamorig:*', metres); the
pack's rig is 'mixamorigN:*' in centimetres. Same skeleton, so a clip
carries over by renaming its channels and scaling every bone translation by
the ratio of the two hip heights (as tools/free-kick-3d/build_character.py).
Then, with Node (gltf-transform 4.1.1): strip_moves.mjs drops the fingers,
scale channels and the rig's own empty take (the exporter samples every
bone), and `gltf-transform optimize ... --compress meshopt --simplify false
--join false --flatten false` gives public/career-3d/footballer-moves.glb
(~140 KB). Docker commands: see the free-kick tools' README (same image).
Clip names are the ones lib/footballerMotion.ts plays."""
import os
import re

import bpy

src, moves, out = '/pack', '/moves', '/work/out'
os.makedirs(out, exist_ok=True)

# Our clip name -> the downloaded file.
CLIPS = {
    'run': 'Running',
    'sprint': 'Sprint',
    'run_back': 'Run Backward',
    'header': 'Soccer Header',
    'celebrate': 'Joyful Jump',
    'victory': 'Victory',
}
FINGERS = re.compile(r'Hand(Thumb|Index|Middle|Ring|Pinky)\d')

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f'{src}/Ch38_nonPBR.fbx')
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
arm.name = 'Footballer'
for o in list(bpy.data.objects):
    if o.type == 'MESH':
        bpy.data.objects.remove(o, do_unlink=True)
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action = None
hips = next(b for b in arm.data.bones if b.name.endswith('Hips'))
prefix = hips.name[:-len('Hips')]
new_hips = hips.head_local.length
print('RIG', prefix, round(new_hips, 3))


def fcurves(act):
    # Blender 5: actions are layered.
    if len(getattr(act, 'fcurves', [])) > 0:
        return list(act.fcurves)
    return [fc for layer in act.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]


def drop(act, fc):
    if len(getattr(act, 'fcurves', [])) > 0:
        act.fcurves.remove(fc)
        return
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                if fc in list(cb.fcurves):
                    cb.fcurves.remove(fc)
                    return


arm.animation_data_create()
for clip, fname in CLIPS.items():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f'{moves}/{fname}.fbx')
    new = [o for o in bpy.data.objects if o not in before]
    a = [o for o in new if o.type == 'ARMATURE'][0]
    act = a.animation_data.action
    act.name = clip
    act.use_fake_user = True
    k = new_hips / next(b for b in a.data.bones if b.name.endswith('Hips')).head_local.length
    for fc in fcurves(act):
        if FINGERS.search(fc.data_path):
            drop(act, fc)
            continue
        fc.data_path = re.sub(r'mixamorig\d*:', prefix, fc.data_path)
        if fc.data_path.endswith('location'):
            for kp in fc.keyframe_points:
                kp.co.y *= k
                kp.handle_left.y *= k
                kp.handle_right.y *= k
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, int(act.frame_range[0]), act)
    track.mute = True
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    print('CLIP', clip, tuple(act.frame_range), 'scale', round(k, 4))

bpy.ops.export_scene.gltf(
    filepath=f'{out}/footballer-moves.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_morph=False, export_def_bones=True,
)
print('SIZE', os.path.getsize(f'{out}/footballer-moves.glb') // 1024, 'KB')
