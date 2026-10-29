# Free kick 3D — footballer model

`frontend/public/free-kick-3d/footballer.glb` is built from the Mixamo
"Soccer" pack (character `Ch38_nonPBR.fbx` + animation FBXs, 30 fps,
"Without Skin"). Not in the repo — keep the pack locally.

1. Blender as a Python module (official `bpy` wheel), in Docker:

   ```bash
   docker run --rm -v "<pack dir>:/pack:ro" -v "$PWD/tools/free-kick-3d:/work" python:3.11-slim \
     sh -c "apt-get update -qq && apt-get install -y -qq libxrender1 libxi6 libxkbcommon0 libsm6 libgl1 libxxf86vm1 libxfixes3 libxext6 libx11-6 \
            && pip install -q bpy && cd /work && python build_footballer.py"
   ```

   It drops the eyelashes, decimates to ~16k polygons, keeps base colour
   and the normal map (body 1024 px — the pack's own size —, hair 512 px), renames the clips (`idle`,
   `wall_jump`, `kick`, `gk_idle`, `gk_dive_left`, `gk_dive_right`,
   `gk_catch`, `gk_fallen`), prints the kick's contact frame and writes
   `out/footballer.glb`.

2. Compress (meshopt geometry/animation, webp textures, meshes kept apart
   so shirt/shorts/socks can be tinted per team):

   ```bash
   npx @gltf-transform/cli@4.1.1 optimize out/footballer.glb footballer.glb \
     --compress meshopt --texture-compress webp --texture-size 1024 \
     --simplify false --join false --flatten false
   ```

If the kick's contact frame changes, update `KICK_CONTACT_T` / `KICK_TOE`
in `frontend/src/components/freeKick3d/Players.tsx`.
