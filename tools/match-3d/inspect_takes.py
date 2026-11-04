"""Timelines of the sources build_moves.py cuts from: what each take or pack
clip does, frame by frame, to pick ranges and contact frames.

    python inspect_takes.py [-- <file stem> ...]     # default: all of /mocap and /pack

Writes one block per source to stdout: every STEP frames the frame, hips
position (metres, x side / y fwd), hips yaw (deg), left/right foot heights,
foot speeds (m/s), hands' and head's heights.
"""
import glob
import math
import os
import sys

import bpy

only = set(sys.argv[sys.argv.index('--') + 1:]) if '--' in sys.argv else set()
paths = sorted(glob.glob('/mocap/*.fbx')) + sorted(glob.glob('/pack/*.fbx'))
NAMES = {
    'hips': ('Hips',), 'lf': ('LeftFoot',), 'rf': ('RightFoot',), 'lt': ('LeftToeBase', 'LeftToe'),
    'rt': ('RightToeBase', 'RightToe'), 'lh': ('LeftHand',), 'rh': ('RightHand',), 'head': ('Head',),
    'lu': ('LeftUpLeg', 'LeftThigh'), 'ru': ('RightUpLeg', 'RightThigh'),
}


def bone(arm, names):
    for b in arm.pose.bones:
        short = b.name.split(':')[-1]
        if short in names:
            return b
    raise KeyError(names)


for path in paths:
    name = os.path.basename(path)[:-4]
    if name.startswith('Ch38') or (only and name not in only):
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if not arms or not arms[0].animation_data or not arms[0].animation_data.action:
        print(f'## {name}: no action')
        continue
    arm = arms[0]
    f0, f1 = (int(x) for x in arm.animation_data.action.frame_range)
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    bs = {k: bone(arm, v) for k, v in NAMES.items()}
    tr = {k: [] for k in bs}
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        for k, b in bs.items():
            tr[k].append((arm.matrix_world @ b.head).copy())
    # Metres: Rokoko exports in its own scale, so unit by the rest height.
    h = max(p.z for p in tr['head'])
    low = min(min(p.z for p in tr['lf']), min(p.z for p in tr['rf']))
    print(f'## {name} frames {f0}..{f1} fps {fps:.0f} ({(f1 - f0) / fps:.2f}s) head max z {h:.3f} foot min {low:.3f}')
    unit = 1.0 if h < 3 else 0.01
    step = max(1, round(fps / 10))
    print('frame   t    hipsX hipsY hipsZ  yaw  footL footR  spdL spdR  handL handR head')
    for i in range(0, len(tr['hips']), step):
        p = tr['hips'][i]
        d = tr['lu'][i] - tr['ru'][i]
        yaw = math.degrees(math.atan2(d.y, d.x))
        j = max(i - 1, 0)
        k = min(i + 1, len(tr['hips']) - 1)
        sl = (tr['lf'][k] - tr['lf'][j]).length * unit * fps / max(k - j, 1)
        sr = (tr['rf'][k] - tr['rf'][j]).length * unit * fps / max(k - j, 1)
        print(f'{f0 + i:5d} {i / fps:5.2f} {p.x * unit:+5.2f} {p.y * unit:+5.2f} {p.z * unit:5.2f} {yaw:+5.0f} '
              f'{tr["lf"][i].z * unit:5.2f} {tr["rf"][i].z * unit:5.2f} {sl:5.1f} {sr:5.1f} '
              f'{tr["lh"][i].z * unit:5.2f} {tr["rh"][i].z * unit:5.2f} {tr["head"][i].z * unit:5.2f}')
