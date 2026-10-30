"""A generated character (Mixamo auto-rig, "T-Pose", FBX Binary, With Skin)
with the "Soccer" pack's clips retargeted onto it -> out/<name>.glb.

    python build_character.py <tpose.fbx> <name>

The pack's rig names its bones 'mixamorigN:*' and works in centimetres;
an auto-rigged character has 'mixamorig:*' in metres. Same skeleton, so a
clip carries over by renaming its channels and scaling every bone
translation by the ratio of the two hip heights.

Also prints, as fractions of the height in the bind pose, where the kit's
white starts and ends (socks / shorts / shirt) — the game tints the kit
by those bands — and the kick's contact frame and toe position."""
import os
import re
import sys

import bpy
import mathutils

src = '/pack'
out = '/work/out'
os.makedirs(out, exist_ok=True)
fbx, name = sys.argv[-2], sys.argv[-1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
mesh = [o for o in bpy.data.objects if o.type == 'MESH'][0]
arm.name = 'Footballer'
mesh.name = 'Body'
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action = None

# Base colour only, 1024 px.
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    for n in list(mat.node_tree.nodes):
        if n.type != 'TEX_IMAGE':
            continue
        if any(l.to_socket.name == 'Base Color' for l in n.outputs[0].links):
            if n.image.size[0] > 1024:
                n.image.scale(1024, 1024)
        else:
            mat.node_tree.nodes.remove(n)
    bsdf = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
    if bsdf:
        bsdf[0].inputs['Roughness'].default_value = 0.75
        bsdf[0].inputs['Metallic'].default_value = 0.0


def fcurves(act):
    # Blender 5: actions are layered.
    if len(getattr(act, 'fcurves', [])) > 0:
        return list(act.fcurves)
    return [fc for layer in act.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]


new_hips = arm.data.bones['mixamorig:Hips'].head_local.length

CLIPS = {
    'gk_idle': 'goalkeeper idle',
    'gk_dive_left': 'goalkeeper diving save',
    'gk_dive_right': 'goalkeeper diving save (2)',
    'gk_catch': 'goalkeeper catch (2)',
    'gk_jump': 'goalkeeper catch (4)',
    'gk_block_left': 'goalkeeper body block',
    'gk_block_right': 'goalkeeper body block (2)',
    'gk_fallen': 'fallen idle',
    'idle': 'offensive idle',
    'wall_jump': 'header soccerball',
    'kick': 'soccer penalty kick',
    # Not in the pack: Mixamo's "Victory", downloaded on its own and put
    # next to the pack's files under this name.
    'celebrate': 'x victory',
    # Mixamo's "Silly Dancing": the «Смешной танец» bought for Stars.
    'silly_dance': 'x silly dancing',
}
arm.animation_data_create()
for clip, fname in CLIPS.items():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f'{src}/{fname}.fbx')
    new = [o for o in bpy.data.objects if o not in before]
    a = [o for o in new if o.type == 'ARMATURE'][0]
    act = a.animation_data.action
    act.name = clip
    act.use_fake_user = True
    k = new_hips / [b for b in a.data.bones if b.name.endswith(':Hips')][0].head_local.length
    for fc in fcurves(act):
        fc.data_path = re.sub(r'mixamorig\d*:', 'mixamorig:', fc.data_path)
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
    print('CLIP', clip, tuple(act.frame_range))

# Kit bands: sample the base colour under every vertex (bind pose).
img = [n.image for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes if n.type == 'TEX_IMAGE'][0]
w, h = img.size
px = list(img.pixels)
uv = mesh.data.uv_layers.active.data
zs = [(mesh.matrix_world @ v.co).z for v in mesh.data.vertices]
z0, z1 = min(zs), max(zs)
kind = {}
for loop in mesh.data.loops:
    u, v = uv[loop.index].uv
    i = (min(h - 1, int((v % 1) * h)) * w + min(w - 1, int((u % 1) * w))) * 4
    r, g, b = px[i:i + 3]
    white = min(r, g, b) > 0.55 and max(r, g, b) - min(r, g, b) < 0.12
    kind.setdefault(loop.vertex_index, []).append(white)
bands = {}
for vi, flags in kind.items():
    f = round((zs[vi] - z0) / (z1 - z0), 2)
    bands.setdefault(f, [0, 0])
    bands[f][0 if sum(flags) * 2 > len(flags) else 1] += 1
print('HEIGHT', round(z1 - z0, 3))
print('BANDS', ' '.join(f'{f}:{c[0]}/{c[1]}' for f, c in sorted(bands.items()) if f < 0.7))

# Kick: the frame the right foot moves fastest = contact with the ball.
arm.animation_data.action = bpy.data.actions['kick']
sc = bpy.context.scene
foot = arm.pose.bones['mixamorig:RightToeBase']
prev = None
best = (0, 0)
for f in range(1, 47):
    sc.frame_set(f)
    p = (arm.matrix_world @ foot.head).copy()
    if prev is not None and (p - prev).length > best[1]:
        best = (f, (p - prev).length)
    prev = p
sc.frame_set(best[0])
p = arm.matrix_world @ foot.head
print('KICK_CONTACT_FRAME', best[0], 'foot_at', tuple(round(x, 2) for x in p))
arm.animation_data.action = None

bpy.ops.export_scene.gltf(
    filepath=f'{out}/{name}.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_image_format='JPEG', export_texcoords=True, export_normals=True,
    export_morph=False, export_def_bones=True,
)
print('SIZE', os.path.getsize(f'{out}/{name}.glb') // 1024, 'KB')
