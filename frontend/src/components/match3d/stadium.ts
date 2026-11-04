/** The ground of «Матч 3D»: a real pitch with crisp lines, two goals whose
 * nets take the ball, a bowl of stands under a roof, boards, masts and sky.
 * All static, a dozen draws; only the nets and the boards move. */
import * as THREE from "three";

import { NET_TILE, daySkyTexture, groundStripsGeometry, ledTexture, lineProfileTexture, netTexture } from "@/components/freeKick3d/textures";
import { BOX_D, BOX_HALF, GOAL_H, GOAL_HALF, HALF_L, HALF_W, NET_DEPTH, PEN_SPOT, SIX_D, SIX_HALF } from "@/lib/match3d/core";

/** Where the sun is (a direction): the shadows on the grass fall from it. */
export const SUN = new THREE.Vector3(-0.42, 1, 0.34);

const arc = (cx: number, cz: number, r: number, from: number, to: number, n = 48): [number, number][] => {
  const out: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const a = from + ((to - from) * i) / n;
    out.push([cx + r * Math.cos(a), cz + r * Math.sin(a)]);
  }
  return out;
};

function markings(): [number, number][][] {
  const L = HALF_L, W = HALF_W;
  const lines: [number, number][][] = [
    [[-L, -W], [L, -W], [L, W], [-L, W], [-L, -W]],
    [[0, -W], [0, W]],
    arc(0, 0, 9.15, 0, Math.PI * 2, 72),
    arc(0, 0, 0.2, 0, Math.PI * 2, 10),
  ];
  for (const d of [1, -1]) {
    lines.push(
      [[d * L, -BOX_HALF], [d * (L - BOX_D), -BOX_HALF], [d * (L - BOX_D), BOX_HALF], [d * L, BOX_HALF]],
      [[d * L, -SIX_HALF], [d * (L - SIX_D), -SIX_HALF], [d * (L - SIX_D), SIX_HALF], [d * L, SIX_HALF]],
      arc(d * (L - PEN_SPOT), 0, 0.16, 0, Math.PI * 2, 8),
    );
    const a = Math.acos((BOX_D - PEN_SPOT) / 9.15);
    lines.push(d > 0 ? arc(L - PEN_SPOT, 0, 9.15, Math.PI - a, Math.PI + a, 24) : arc(-L + PEN_SPOT, 0, 9.15, -a, a, 24));
    for (const e of [1, -1]) lines.push(arc(d * L, e * W, 1, d * e > 0 ? Math.PI : d > 0 ? Math.PI / 2 : 0, d * e > 0 ? Math.PI * 1.5 : d > 0 ? Math.PI : Math.PI / 2, 8));
  }
  return lines;
}

/** One side of a net as a grid (the ball pushes the grid). */
function netSheet(w: number, h: number, nx: number, ny: number, place: (u: number, v: number, out: THREE.Vector3) => void) {
  const pos: number[] = [], uv: number[] = [], index: number[] = [];
  const p = new THREE.Vector3();
  for (let j = 0; j <= ny; j++) {
    for (let i = 0; i <= nx; i++) {
      place(i / nx, j / ny, p);
      pos.push(p.x, p.y, p.z);
      uv.push(((i / nx) * w) / NET_TILE.w, ((j / ny) * h) / NET_TILE.h);
    }
  }
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1;
      index.push(a, b, d, a, d, c);
    }
  }
  return { pos, uv, index };
}

const POST = 0.06;

type Net = { uniform: { value: THREE.Vector4 }; force: number; vel: number; y: number; z: number };

function goal(side: 1 | -1, group: THREE.Group, tex: THREE.Texture): Net {
  const g = new THREE.Group();
  g.position.x = side * HALF_L;
  if (side < 0) g.rotation.y = Math.PI;
  const white = new THREE.MeshLambertMaterial({ color: "#f7f7f4" });
  const tube = (len: number) => new THREE.CylinderGeometry(POST, POST, len, 10);
  for (const z of [-1, 1]) {
    const post = new THREE.Mesh(tube(GOAL_H + POST), white);
    post.position.set(POST, (GOAL_H + POST) / 2, z * (GOAL_HALF + POST));
    g.add(post);
  }
  const bar = new THREE.Mesh(tube(GOAL_HALF * 2 + POST * 3), white);
  bar.rotation.x = Math.PI / 2;
  bar.position.set(POST, GOAL_H + POST, 0);
  g.add(bar);
  // The stanchions behind the net.
  const dark = new THREE.MeshLambertMaterial({ color: "#a9adb2" });
  const thin = (a: THREE.Vector3, b: THREE.Vector3) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, a.distanceTo(b), 6), dark);
    m.position.copy(a).lerp(b, 0.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    g.add(m);
  };
  for (const z of [-1, 1]) {
    const edge = z * (GOAL_HALF + POST);
    thin(new THREE.Vector3(POST, GOAL_H, edge), new THREE.Vector3(NET_DEPTH, 0.75, edge));
    thin(new THREE.Vector3(NET_DEPTH, 0.75, edge), new THREE.Vector3(NET_DEPTH, 0, edge));
    thin(new THREE.Vector3(NET_DEPTH, 0, edge), new THREE.Vector3(POST, 0, edge));
  }
  // The net: back, roof and both sides as one mesh.
  const hw = GOAL_HALF + POST;
  const backProfile = (v: number) => {
    // v = 0 on the ground at the back, 1 up at the bar's level, a sagging slope.
    const y = v * GOAL_H;
    const x = v < 0.3 ? NET_DEPTH : NET_DEPTH - (v - 0.3) * (NET_DEPTH - 0.6) * 1.1;
    return { x, y };
  };
  const sheets = [
    netSheet(hw * 2, GOAL_H + 1.4, 18, 10, (u, v, o) => {
      const { x, y } = backProfile(v);
      o.set(x, y, (u * 2 - 1) * hw);
    }),
    netSheet(0.9, hw * 2, 3, 12, (u, v, o) => o.set(POST + (1 - u) * 0.5, GOAL_H - u * 0.02, (v * 2 - 1) * hw)),
    ...[-1, 1].map((z) => netSheet(NET_DEPTH, GOAL_H, 8, 8, (u, v, o) => {
      const top = backProfile(v).x;
      o.set(POST + u * (top - POST), v * GOAL_H, z * hw);
    })),
  ];
  const pos: number[] = [], uv: number[] = [], index: number[] = [];
  for (const s of sheets) {
    const base = pos.length / 3;
    pos.push(...s.pos);
    uv.push(...s.uv);
    index.push(...s.index.map((i) => i + base));
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(index);
  const uniform = { value: new THREE.Vector4(0, 1, 0, 0) };
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, depthWrite: false, opacity: 0.95, toneMapped: false });
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uNet = uniform;
    sh.vertexShader = (`uniform vec4 uNet;\n` + sh.vertexShader).replace(
      "#include <begin_vertex>",
      `vec3 transformed = position;
       float nd = distance(position.yz, uNet.xy);
       float nk = exp(-nd * nd * 0.75) * smoothstep(0.1, 1.2, position.x);
       transformed.x += uNet.z * nk;
       transformed.y += uNet.w * nk;`,
    );
  };
  mat.customProgramCacheKey = () => "match3d-net";
  const net = new THREE.Mesh(geo, mat);
  net.frustumCulled = false;
  net.renderOrder = 2;
  g.add(net);
  group.add(g);
  return { uniform, force: 0, vel: 0, y: 1, z: 0 };
}

/** A tier of the bowl: rounded-rectangle rings from the low edge to the high one. */
function tier(a0: number, b0: number, y0: number, a1: number, b1: number, y1: number, repeatU: number): THREE.BufferGeometry {
  const seg = 96, power = 0.42;
  const ring = (t: number, a: number, b: number) => {
    const c = Math.cos(t), s = Math.sin(t);
    return [Math.sign(c) * Math.abs(c) ** power * a, Math.sign(s) * Math.abs(s) ** power * b] as const;
  };
  const pos: number[] = [], uv: number[] = [], index: number[] = [];
  for (let i = 0; i <= seg; i++) {
    const t = (i / seg) * Math.PI * 2;
    const [x0, z0] = ring(t, a0, b0);
    const [x1, z1] = ring(t, a1, b1);
    pos.push(x0, y0, z0, x1, y1, z1);
    uv.push((i / seg) * repeatU, 0, (i / seg) * repeatU, 1);
    if (i < seg) {
      const k = i * 2;
      index.push(k, k + 2, k + 1, k + 1, k + 2, k + 3);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(index);
  geo.computeVertexNormals();
  return geo;
}

function pitchMaterial(grass: THREE.Texture) {
  const mat = new THREE.MeshLambertMaterial({ map: grass, color: "#ffffff" });
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = ("varying vec2 vMcWorld;\n" + sh.vertexShader).replace(
      "#include <begin_vertex>",
      "#include <begin_vertex>\nvMcWorld = position.xz;",
    );
    sh.fragmentShader = (`varying vec2 vMcWorld;
uniform vec2 uHalf;
` + sh.fragmentShader).replace(
      "#include <map_fragment>",
      `#include <map_fragment>
       float inside = step(abs(vMcWorld.x), uHalf.x + 2.) * step(abs(vMcWorld.y), uHalf.y + 2.);
       float along = fract((vMcWorld.x + uHalf.x) / 11.667 * .5);
       float band = smoothstep(.0, .012, along - .5) * (1. - smoothstep(.0, .012, along - .988));
       float across = fract((vMcWorld.y + uHalf.y) / 11.333 * .5);
       float cross = smoothstep(.0, .02, across - .5) * (1. - smoothstep(.0, .02, across - .98));
       float mow = mix(mix(.93, 1.07, band), mix(1., 1.14, band), cross);
       vec3 turf = mix(vec3(.30, .42, .24), vec3(.44, .62, .34) * mow, inside * .9 + .1);
       diffuseColor.rgb = diffuseColor.rgb * 1.95 * turf;
       // The near stand's shadow on the touchline, with a soft, curved edge.
       float edge = uHalf.y - 9. - 1.4 * sin(vMcWorld.x * .035) - vMcWorld.x * .06;
       diffuseColor.rgb *= mix(1., .7, smoothstep(edge - .5, edge + .5, vMcWorld.y));`,
    );
    sh.uniforms.uHalf = { value: new THREE.Vector2(HALF_L, HALF_W) };
  };
  mat.customProgramCacheKey = () => "match3d-pitch";
  return mat;
}

export type Stadium = {
  group: THREE.Group;
  /** The ball went into this end's net, at this height and across position, this hard. */
  netHit: (end: 1 | -1, y: number, z: number, speed: number) => void;
  update: (dt: number) => void;
  dispose: () => void;
};

const SIGN_L = "FOOTY CARDS";
const SIGN_R = "МАТЧ 3D";

export function makeStadium(textures: { grass: THREE.Texture; stands: THREE.Texture; fans: THREE.Texture | null; led: THREE.Texture }): Stadium {
  const group = new THREE.Group();
  const disposable: (THREE.BufferGeometry | THREE.Material | THREE.Texture)[] = [];
  const add = <T extends THREE.Object3D>(o: T) => { group.add(o); return o; };
  const own = <T extends THREE.BufferGeometry | THREE.Material | THREE.Texture>(x: T) => { disposable.push(x); return x; };

  const sky = own(daySkyTexture());
  add(new THREE.Mesh(own(new THREE.SphereGeometry(420, 24, 16)), own(new THREE.MeshBasicMaterial({ map: sky, side: THREE.BackSide, fog: false, depthWrite: false, toneMapped: false }))));

  textures.grass.wrapS = textures.grass.wrapT = THREE.RepeatWrapping;
  textures.grass.repeat.set(24, 17);
  textures.grass.anisotropy = 8;
  const ground = add(new THREE.Mesh(own(new THREE.PlaneGeometry(160, 110)), own(pitchMaterial(textures.grass))));
  // Laid flat in its own coordinates: the shader reads the pitch from them.
  ground.geometry.rotateX(-Math.PI / 2);

  const profile = own(lineProfileTexture());
  profile.generateMipmaps = true;
  const lines = add(new THREE.Mesh(
    own(groundStripsGeometry(markings(), 0.26)),
    own(new THREE.MeshBasicMaterial({ color: "#ffffff", alphaMap: profile, transparent: true, depthWrite: false, opacity: 0.96 })),
  ));
  lines.position.y = 0.012;
  lines.renderOrder = 0;

  const netTex = own(netTexture());
  netTex.wrapS = netTex.wrapT = THREE.RepeatWrapping;
  netTex.anisotropy = 4;
  netTex.generateMipmaps = true;
  const nets: Record<string, Net> = { "1": goal(1, group, netTex), "-1": goal(-1, group, netTex) };

  // The stands: two tiers of people, a band between them, and a roof.
  const st = textures.stands;
  st.wrapS = THREE.RepeatWrapping;
  st.anisotropy = 4;
  const crowdMat = own(new THREE.MeshBasicMaterial({ map: st, color: "#d9dade" }));
  add(new THREE.Mesh(own(tier(61, 43, 1.2, 84, 66, 15, 16)), crowdMat));
  add(new THREE.Mesh(own(tier(86, 68, 19, 112, 94, 42, 20)), crowdMat));
  add(new THREE.Mesh(own(tier(84, 66, 15, 86, 68, 19, 8)), own(new THREE.MeshBasicMaterial({ color: "#20344e" }))));
  add(new THREE.Mesh(own(tier(112, 94, 42, 88, 70, 51, 8)), own(new THREE.MeshBasicMaterial({ color: "#c7ced8", side: THREE.DoubleSide }))));
  add(new THREE.Mesh(own(tier(58, 40, 0, 61, 43, 1.2, 8)), own(new THREE.MeshBasicMaterial({ color: "#1d2c3f" }))));

  // Boards along the far side and behind the goals, each with its own scroll.
  const boards: THREE.Texture[] = [];
  const board = (x: number, z: number, w: number, r: number, text: string, accent: string) => {
    const tex = own(ledTexture(text, accent));
    tex.repeat.set(w / 16, 1);
    boards.push(tex);
    const b = add(new THREE.Mesh(own(new THREE.PlaneGeometry(w, 1.1)), own(new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }))));
    b.position.set(x, 0.6, z);
    b.rotation.y = r;
  };
  board(0, -HALF_W - 4.6, 122, 0, SIGN_L, "#ffffff");
  board(-HALF_L - 5, -20, 40, Math.PI / 2, SIGN_R, "#7cd1ff");
  board(-HALF_L - 5, 20, 40, Math.PI / 2, SIGN_L, "#ffffff");
  board(HALF_L + 5, -20, 40, -Math.PI / 2, SIGN_L, "#ffffff");
  board(HALF_L + 5, 20, 40, -Math.PI / 2, SIGN_R, "#7cd1ff");

  // Corner flags.
  const flagCloth = own(new THREE.MeshBasicMaterial({ color: "#f5d90a", side: THREE.DoubleSide }));
  const pole = own(new THREE.CylinderGeometry(0.02, 0.02, 1.5, 6));
  const clothGeo = own(new THREE.PlaneGeometry(0.4, 0.28));
  for (const x of [-1, 1]) {
    for (const z of [-1, 1]) {
      const m = add(new THREE.Mesh(pole, own(new THREE.MeshLambertMaterial({ color: "#ffffff" }))));
      m.position.set(x * HALF_L, 0.75, z * HALF_W);
      const c = add(new THREE.Mesh(clothGeo, flagCloth));
      c.position.set(x * HALF_L + 0.2, 1.36, z * HALF_W);
    }
  }

  // Masts over the roof corners, their lamps lit in the afternoon haze.
  const lamp = own(new THREE.MeshBasicMaterial({ color: "#fffbe6", toneMapped: false }));
  const mast = own(new THREE.MeshLambertMaterial({ color: "#6e7886" }));
  for (const x of [-1, 1]) {
    for (const z of [-1, 1]) {
      const p = add(new THREE.Mesh(own(new THREE.CylinderGeometry(0.6, 1, 62, 8)), mast));
      p.position.set(x * 104, 31, z * 84);
      const panel = add(new THREE.Mesh(own(new THREE.BoxGeometry(14, 7, 0.8)), mast));
      panel.position.set(x * 102, 64, z * 82);
      panel.lookAt(0, 0, 0);
      const lit = add(new THREE.Mesh(own(new THREE.PlaneGeometry(12.6, 5.8)), lamp));
      lit.position.copy(panel.position).multiplyScalar(0.992);
      lit.lookAt(0, 0, 0);
    }
  }

  return {
    group,
    netHit: (end, y, z, speed) => {
      const n = nets[String(end)];
      n.y = y; n.z = end > 0 ? z : -z;
      n.vel = Math.min(speed, 30) * 0.16;
    },
    update: (dt) => {
      for (const n of [nets["1"], nets["-1"]]) {
        // A damped spring.
        n.vel += (-n.force * 90 - n.vel * 7) * dt;
        n.force += n.vel * dt;
        n.uniform.value.set(n.y, n.z, n.force, Math.max(n.force, 0) * -0.25);
      }
      boards.forEach((t, i) => { t.offset.x += dt * (i % 2 ? 0.05 : -0.05); });
    },
    dispose: () => disposable.forEach((d) => d.dispose()),
  };
}
