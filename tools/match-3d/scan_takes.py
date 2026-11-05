"""Measures what inspect_takes.py can't show by eye:

    python scan_takes.py

- loops: for stretches of the mocap takes, the frame pairs whose pose AND
  velocities match best (in the body's own frame), with the net travel and
  turn across the cycle;
- lean: moments a footballer stands with the torso leaned back (a chest
  trap), from the juggling takes and the pack;
- hands: how close a hand gets to the head, for a dejected pose.
"""
import glob
import math
import os

import bpy
from mathutils import Vector

# take -> stretches (60 fps) and the cycle length range.
LOOPS = {
    '01_Dribble_01': [(13, 60, 24, 48), (225, 300, 30, 60)],
    '02_Dribble_02': [(487, 541, 24, 50)],
    '03_Dribble_03': [(97, 205, 30, 96)],
    '18_Defending_01': [(13, 270, 36, 130)],
    '19_Defending_02': [(13, 240, 36, 130), (300, 430, 36, 120)],
}
PARTS = {
    'hips': ('Hips',), 'lf': ('LeftFoot',), 'rf': ('RightFoot',), 'lh': ('LeftHand',), 'rh': ('RightHand',),
    'head': ('Head',), 'lu': ('LeftUpLeg', 'LeftThigh'), 'ru': ('RightUpLeg', 'RightThigh'),
}


def bone(arm, names):
    for b in arm.pose.bones:
        if b.name.split(':')[-1] in names:
            return b
    raise KeyError(names)


def sample(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
    f0, f1 = (int(x) for x in arm.animation_data.action.frame_range)
    sc = bpy.context.scene
    bs = {k: bone(arm, v) for k, v in PARTS.items()}
    frames = {}
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        frames[f] = {k: (arm.matrix_world @ b.head).copy() for k, b in bs.items()}
    return frames, sc.render.fps / sc.render.fps_base


def body(fr):
    """Left and forward (unit, horizontal) of the pelvis."""
    d = fr['lu'] - fr['ru']
    left = Vector((d.x, d.y, 0)).normalized()
    return left, Vector((left.y, -left.x, 0))


def yaw(fr):
    d = fr['lu'] - fr['ru']
    return math.degrees(math.atan2(d.y, d.x))


def features(frames, f):
    fr = frames[f]
    left, fwd = body(fr)
    v = [fr['hips'].z]
    for k in ('lf', 'rf', 'lh', 'rh', 'head'):
        p = fr[k] - fr['hips']
        v += [p.dot(left), p.dot(fwd), p.z]
    return v


def scan_loops(name, frames):
    for a, b, lo, hi in LOOPS[name]:
        feats = {f: features(frames, f) for f in range(a, b + 1)}
        found = []
        for i in range(a + 2, b - lo):
            for j in range(i + lo, min(i + hi, b - 2) + 1):
                if (j - i) % 2:
                    continue
                d = sum((x - y) ** 2 for x, y in zip(feats[i], feats[j]))
                dv = sum(((p - q) - (r - s)) ** 2 for p, q, r, s in zip(feats[i + 2], feats[i - 2], feats[j + 2], feats[j - 2]))
                found.append((math.sqrt(d / len(feats[i])) + 0.5 * math.sqrt(dv / len(feats[i])), i, j))
        found.sort()
        taken = []
        for score, i, j in found:
            if any(abs(i - p) < 8 and abs(j - q) < 8 for p, q in taken):
                continue
            taken.append((i, j))
            left, fwd = body(frames[i])
            t = frames[j]['hips'] - frames[i]['hips']
            turn = (yaw(frames[j]) - yaw(frames[i]) + 180) % 360 - 180
            secs = (j - i) / 60
            print(f'LOOP {name} [{a}-{b}] {i}..{j} {secs:.2f}s score {score:.3f} net left {t.dot(left):+.2f} fwd {t.dot(fwd):+.2f} '
                  f'({t.length / secs:.2f} m/s) turn {turn:+.0f}')
            if len(taken) >= 6:
                break


for path in sorted(glob.glob('/mocap/*.fbx')) + sorted(glob.glob('/pack/*.fbx')):
    name = os.path.basename(path)[:-4]
    if name.startswith('Ch38'):
        continue
    frames, fps = sample(path)
    if name in LOOPS:
        scan_loops(name, frames)
    # Skip the T-pose at the head of a take.
    keys = [f for f in frames if f > frames.__iter__().__next__() + (12 if fps > 40 else 0)]
    lean, near = (0, None), (9, None)
    for f in keys:
        fr = frames[f]
        left, fwd = body(fr)
        p = fr['head'] - fr['hips']
        a = math.degrees(math.atan2(p.dot(fwd), p.z))
        grounded = min(fr['lf'].z, fr['rf'].z) < 0.16 and fr['hips'].z > 0.7
        if grounded and a < lean[0]:
            lean = (a, f)
        unit = 0.01 if fr['head'].z > 3 else 1
        d = min((fr['lh'] - fr['head']).length, (fr['rh'] - fr['head']).length) * unit
        if d < near[0]:
            near = (d, f)
    both = min(((frames[f]['lh'] - frames[f]['head']).length + (frames[f]['rh'] - frames[f]['head']).length, f) for f in keys)
    print(f'POSE {name}: lean back {lean[0]:+.0f} at {lean[1]}; nearest hand-head {near[0]:.2f} at {near[1]}; both hands {both[0]:.2f} at {both[1]}')
