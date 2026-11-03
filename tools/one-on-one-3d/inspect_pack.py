"""Prints what each clip of the Mixamo "Soccer" pack does, to pick the ones
«Атака 1 на 1» plays: length, how far the hips travel, which foot moves
fastest and when (the kick's contact), how high the hands get.

    python inspect_pack.py            # the pack mounted at /pack
"""
import glob
import os

import bpy
from mathutils import Vector

PACK = '/pack'


def world(arm, name):
    b = arm.pose.bones.get(name)
    return arm.matrix_world @ b.head if b else None


for path in sorted(glob.glob(f'{PACK}/*.fbx')):
    name = os.path.basename(path)[:-4]
    if name.startswith('Ch38'):
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if not arms or not arms[0].animation_data or not arms[0].animation_data.action:
        print(f'{name}: no action')
        continue
    arm = arms[0]
    act = arm.animation_data.action
    f0, f1 = (int(x) for x in act.frame_range)
    fps = bpy.context.scene.render.fps
    hips_name = next(b.name for b in arm.pose.bones if b.name.endswith('Hips'))
    pre = hips_name[:-len('Hips')]
    sc = bpy.context.scene
    track = {k: [] for k in ('hips', 'lt', 'rt', 'lh', 'rh', 'head')}
    bones = {'hips': 'Hips', 'lt': 'LeftToeBase', 'rt': 'RightToeBase', 'lh': 'LeftHand', 'rh': 'RightHand', 'head': 'Head'}
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        for k, b in bones.items():
            track[k].append(world(arm, pre + b).copy())
    unit = (track['head'][0] - (track['lt'][0] + track['rt'][0]) / 2).length or 1

    def peak(key):
        best, at = 0.0, f0
        for i in range(1, len(track[key])):
            sp = (track[key][i] - track[key][i - 1]).length / unit * fps
            if sp > best:
                best, at = sp, f0 + i
        return best, at

    lt, lat = peak('lt')
    rt, rat = peak('rt')
    h0, h1 = track['hips'][0], track['hips'][-1]
    travel = (h1 - h0) / unit
    hands = max(max(p.z for p in track['lh']), max(p.z for p in track['rh'])) / unit
    hips_low = min(p.z for p in track['hips']) / unit
    foot = 'L' if lt > rt * 1.2 else 'R' if rt > lt * 1.2 else '='
    print(f'{name:34s} {pre:12s} {(f1 - f0) / fps:5.2f}s  travel x{travel.x:+.2f} y{travel.y:+.2f} z{travel.z:+.2f} (body heights)'
          f'  toeL {lt:5.1f}@{lat - f0:3d} toeR {rt:5.1f}@{rat - f0:3d} foot {foot}  handsMax {hands:.2f} hipsMin {hips_low:.2f}')
