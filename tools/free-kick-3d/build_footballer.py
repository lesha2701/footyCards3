import bpy, os
src='/pack'; out='/work/out'
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f'{src}/Ch38_nonPBR.fbx')
arm=[o for o in bpy.data.objects if o.type=='ARMATURE'][0]
arm.name='Footballer'
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action=None

RATIOS={'Ch38_Body':0.25,'Ch38_Hair':0.12,'Ch38_Shirt':0.35,'Ch38_Shorts':0.35,'Ch38_Shoes':0.3,'Ch38_Socks':0.6}
for o in list(bpy.data.objects):
    if o.type!='MESH': continue
    if o.name=='Ch38_Eyelashes':
        bpy.data.objects.remove(o); continue
    bpy.context.view_layer.objects.active=o
    for s in bpy.context.selected_objects: s.select_set(False)
    o.select_set(True)
    m=o.modifiers.new('dec','DECIMATE'); m.ratio=RATIOS.get(o.name,0.4)
    bpy.ops.object.modifier_move_to_index(modifier='dec', index=0)
    bpy.ops.object.modifier_apply(modifier='dec')
    print('MESH',o.name,len(o.data.polygons))

# Materials: base colour only, textures down to 1024.
for mat in bpy.data.materials:
    if not mat.use_nodes: continue
    nt=mat.node_tree
    bsdf=[n for n in nt.nodes if n.type=='BSDF_PRINCIPLED']
    keep=None
    for n in list(nt.nodes):
        if n.type=='TEX_IMAGE':
            if any(l.to_socket.name=='Base Color' for l in n.outputs[0].links) and keep is None:
                keep=n
            else:
                nt.nodes.remove(n)
        elif n.type in ('NORMAL_MAP','BUMP'):
            nt.nodes.remove(n)
    if bsdf:
        bsdf[0].inputs['Roughness'].default_value=0.8
        bsdf[0].inputs['Metallic'].default_value=0.0
    if keep and keep.image:
        im=keep.image
        size=256 if mat.name.endswith('_hair') else 1024
        if im.size[0]>size: im.scale(size,size)
        im.filepath_raw=f'{out}/{mat.name}.png'; im.file_format='PNG'; im.save()
        print('TEX',mat.name,im.name,im.size[:])
for im in list(bpy.data.images):
    if im.users==0: bpy.data.images.remove(im)

CLIPS={
 'gk_idle':'goalkeeper idle',
 'gk_dive_left':'goalkeeper diving save',
 'gk_dive_right':'goalkeeper diving save (2)',
 'gk_catch':'goalkeeper catch (2)',
 'gk_fallen':'fallen idle',
 'idle':'offensive idle',
 'wall_jump':'header soccerball',
 'kick':'soccer penalty kick',
}
arm.animation_data_create()
for clip,fname in CLIPS.items():
    before=set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f'{src}/{fname}.fbx')
    new=[o for o in bpy.data.objects if o not in before]
    a=[o for o in new if o.type=='ARMATURE'][0]
    act=a.animation_data.action
    act.name=clip
    act.use_fake_user=True
    track=arm.animation_data.nla_tracks.new(); track.name=clip
    st=track.strips.new(clip,int(act.frame_range[0]),act)
    track.mute=True
    for o in new: bpy.data.objects.remove(o, do_unlink=True)
    print('CLIP',clip,tuple(act.frame_range))

# Kick: the frame the right foot moves fastest = contact with the ball.
arm.animation_data.action=bpy.data.actions['kick']
sc=bpy.context.scene
foot=[b for b in arm.pose.bones if b.name.endswith(':RightToeBase')][0]
prev=None; best=(0,0)
for f in range(1,47):
    sc.frame_set(f)
    p=(arm.matrix_world@foot.head).copy()
    if prev is not None:
        v=(p-prev).length
        if v>best[1]: best=(f,v)
    prev=p
sc.frame_set(best[0]); p=arm.matrix_world@foot.head
print('KICK_CONTACT_FRAME',best[0],'foot_at',tuple(round(x,2) for x in p))
arm.animation_data.action=None

bpy.ops.export_scene.gltf(
    filepath=f'{out}/footballer.glb', export_format='GLB',
    export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_yup=True, export_apply=False,
    export_image_format='WEBP', export_texcoords=True, export_normals=True,
    export_morph=False, export_def_bones=True,
)
print('SIZE', os.path.getsize(f'{out}/footballer.glb')//1024,'KB')
