/** The running match on screen: steps the engine at a fixed 60 Hz, turns its
 * state into people, a ball, a broadcast camera and sound, keeps the last few
 * seconds for the replay of a goal. It only ever reads the simulation; what
 * the human does reaches it as one `Input` per tick. */
import * as THREE from "three";

import { ballGeometry } from "@/components/freeKick3d/textures";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import {
  Act, BALL_R, HALF_L, HALF_W, HZ, Kick, PRED_STEP, Phase, TICK, type MatchEvent, type MatchState, type Setup,
} from "@/lib/match3d/core";
import { clockText, createMatch, passTarget, stepMatch, type Input, type Press } from "@/lib/match3d/engine";

import type { MatchAssets } from "./assets";
import { Motion } from "./motion";
import { PEOPLE, REFEREE, makeSquad, type Look, type Squad } from "./squad";
import { SUN, makeStadium, type Stadium } from "./stadium";
import { whistle } from "./whistle";

const HOME = { shirt: "#d4202f", shorts: "#ffffff", socks: "#d4202f" };
const AWAY = { shirt: "#f2f4f8", shorts: "#1c3f94", socks: "#1c3f94" };
const KEEPER_HOME = { shirt: "#1bb36b", shorts: "#10243d", socks: "#1bb36b" };
const KEEPER_AWAY = { shirt: "#f7c81e", shorts: "#2a2a2a", socks: "#f7c81e" };
const OFFICIAL = { shirt: "#16181d", shorts: "#16181d", socks: "#16181d" };
const SKINS = ["#f1d2bd", "#e6b896", "#c98f68", "#7a4a32", "#f4dcc9", "#9c6646", "#e0ac86"];
const HAIRS = ["#2b1d14", "#3a2a20", "#14100d", "#6b4a2c", "#a97c42", "#20160f"];

function looks(seed: number): Look[] {
  const out: Look[] = [];
  for (let i = 0; i < PEOPLE; i++) {
    const n = Math.imul(i + 3, seed | 1) >>> 7;
    const kit = i >= 22 ? OFFICIAL : i === 0 ? KEEPER_HOME : i === 11 ? KEEPER_AWAY : i < 11 ? HOME : AWAY;
    out.push({ kit, skin: SKINS[n % SKINS.length], hair: HAIRS[(n >>> 3) % HAIRS.length] });
  }
  return out;
}

export type GameEnd = { home: string; away: string; g0: number; g1: number; s: MatchState };

export type Hud = {
  g0: number; g1: number; clock: string;
  /** The human's team has the ball at his feet, or he takes the restart. */
  attack: boolean;
  /** He stands over a set piece. */
  setKind: string | null;
  /** The ball is in his keeper's hands, or he takes the goal kick. */
  keeper: boolean;
  /** In front of goal: the lofted ball here is the chip. */
  chipHere: boolean;
  replay: boolean;
  ended: boolean;
};

export type GameHooks = {
  onHud: (h: Hud) => void;
  onMessage: (text: string, big?: boolean) => void;
  onEnd: (e: GameEnd) => void;
};

const FPS_SAMPLE = 90;
const DPR_MIN = 1;
const DPR_MAX = 1.75;
const NEAR_LOD = 46;
const RING = 420;
const REC = 3 + 7 * PEOPLE;
const REPLAY_RATE = 0.5;
/** Ticks into the celebration when the replay cuts in. */
const REPLAY_AT = 170;

const shortest = (a: number, b: number) => {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
};
const damp = (k: number, dt: number) => 1 - Math.exp(-k * dt);

export class MatchGame {
  readonly s: MatchState;
  /** Set by the controls. */
  readonly stick = { x: 0, y: 0 };
  sprint = false;
  contain = false;
  paused = false;

  private press: Press | null = null;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(24, 2, 1, 900);
  private readonly stadium: Stadium;
  private readonly squad: Squad;
  private readonly motion: Motion;
  private readonly ball: THREE.Mesh;
  private readonly ballShadow: THREE.Mesh;
  private readonly marker: THREE.Mesh;
  private readonly arrow: THREE.Mesh;
  /** Who a pass would go to right now. */
  private readonly aim: THREE.Mesh;
  private aimAt = -1;
  /** The legs of the human's man, over his head. */
  private readonly legs = new THREE.Group();
  private readonly legsFill: THREE.Mesh;
  private readonly landing: THREE.Mesh;
  private readonly trail: { mesh: THREE.Mesh; pos: Float32Array; at: number; attr: THREE.BufferAttribute; fade: Float32Array; fadeAttr: THREE.BufferAttribute; x: Float32Array; y: Float32Array; z: Float32Array; on: number };
  private readonly px = new Float32Array(22);
  private readonly pz = new Float32Array(22);
  private readonly pa = new Float32Array(22);
  private readonly yaw = new Float32Array(PEOPLE);
  private readonly turned = new Uint8Array(PEOPLE);
  private readonly off = { x: [0, 0, 0], z: [0, 0, 0], vx: [0, 0, 0], vz: [0, 0, 0] };
  private readonly pb = new THREE.Vector3();
  private readonly focus = new THREE.Vector3(0, 0, 0);
  private readonly look = new THREE.Vector3(0, 1, 0);
  private readonly camPos = new THREE.Vector3(0, 20, 60);
  private readonly spin = new THREE.Quaternion();
  private readonly ring = new Float32Array(RING * REC);
  private ringTick = 0;
  private lastKickTick = 0;
  private goalTick = -1;
  private replayF = -1;
  private replayEnd = 0;
  private replayed = false;
  private fov = 24;
  private acc = 0;
  private last = 0;
  private raf = 0;
  private dead = false;
  private frameN = 0;
  private frameSum = 0;
  private dpr: number;
  private hudT = 0;
  private hudKey = "";
  private ended = false;
  private tense = false;
  private readonly stopCrowd: () => void;
  private width = 2;
  private height = 1;
  private readonly tmp = new THREE.Vector3();
  private readonly tmpQ = new THREE.Quaternion();
  private readonly demo: boolean;

  constructor(canvas: HTMLCanvasElement, assets: MatchAssets, setup: Setup, private readonly hooks: GameHooks, demo = false) {
    this.demo = demo;
    this.s = createMatch(setup, demo ? null : 0);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance", stencil: false });
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.02;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.dpr = Math.min(window.devicePixelRatio || 1, DPR_MAX);
    this.renderer.setPixelRatio(this.dpr);

    this.scene.add(new THREE.HemisphereLight("#e4efff", "#6f8d57", 1.55));
    const sun = new THREE.DirectionalLight("#fff0d8", 2.5);
    sun.position.copy(SUN).multiplyScalar(100);
    this.scene.add(sun);

    this.stadium = makeStadium(assets);
    this.scene.add(this.stadium.group);
    this.squad = makeSquad(assets.near, assets.far, assets.baked, assets.map, assets.hairMap, looks(setup.seed));
    this.scene.add(this.squad.group);
    this.motion = new Motion(assets.baked, assets.moves, assets.paces, PEOPLE);

    const geo = ballGeometry();
    geo.computeBoundingSphere();
    const shown = (BALL_R * 1.45) / geo.boundingSphere!.radius;
    this.ball = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ vertexColors: true }));
    this.ball.scale.setScalar(shown);
    this.scene.add(this.ball);
    const blob = new THREE.Mesh(new THREE.CircleGeometry(BALL_R * 1.5, 18), new THREE.MeshBasicMaterial({ color: "#071a0c", transparent: true, opacity: 0.45, depthWrite: false }));
    blob.rotation.x = -Math.PI / 2;
    this.ballShadow = blob;
    this.scene.add(blob);

    this.marker = new THREE.Mesh(new THREE.RingGeometry(0.62, 0.8, 36), new THREE.MeshBasicMaterial({ color: "#d6ff3f", transparent: true, opacity: 0.92, depthWrite: false, toneMapped: false }));
    this.marker.rotation.x = -Math.PI / 2;
    this.marker.renderOrder = 1;
    this.scene.add(this.marker);
    this.arrow = new THREE.Mesh(new THREE.ConeGeometry(0.26, 0.42, 4), new THREE.MeshBasicMaterial({ color: "#d6ff3f", toneMapped: false }));
    this.arrow.rotation.x = Math.PI;
    this.scene.add(this.arrow);
    this.aim = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.68, 28), new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.85, depthWrite: false, toneMapped: false }));
    this.aim.rotation.x = -Math.PI / 2;
    this.aim.renderOrder = 1;
    this.aim.visible = false;
    this.scene.add(this.aim);
    const bar = new THREE.PlaneGeometry(1, 1);
    bar.translate(0.5, 0, 0);
    const back = new THREE.Mesh(bar, new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.6, depthTest: false, depthWrite: false, toneMapped: false }));
    back.position.x = -0.6;
    back.scale.set(1.2, 0.17, 1);
    back.renderOrder = 5;
    this.legsFill = new THREE.Mesh(bar, new THREE.MeshBasicMaterial({ color: "#d6ff3f", transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    this.legsFill.position.set(-0.56, 0, 0.001);
    this.legsFill.renderOrder = 6;
    this.legs.add(back, this.legsFill);
    this.legs.visible = false;
    this.scene.add(this.legs);
    this.landing = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.46, 24), new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.55, depthWrite: false, toneMapped: false }));
    this.landing.rotation.x = -Math.PI / 2;
    this.landing.visible = false;
    this.scene.add(this.landing);

    this.trail = this.makeTrail();
    this.stopCrowd = startCrowd();
    this.motion.snap(this.s);
    this.savePrev();
    this.focus.set(this.s.ball.x, 0, this.s.ball.z);
    this.off.x = [0, 22, -22];
    this.off.z = [-14, -HALF_W - 1, HALF_W + 1];
    this.last = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  /** Called with the box's size in CSS pixels (the landscape box, rotated or not). */
  resize(w: number, h: number) {
    this.width = w;
    this.height = h;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  /** A button was let go. */
  act(press: Press) {
    if (this.replayF >= 0) {
      this.endReplay();
      return;
    }
    this.press = press;
  }

  skipReplay() {
    if (this.replayF >= 0) this.endReplay();
  }

  dispose() {
    this.dead = true;
    cancelAnimationFrame(this.raf);
    this.stopCrowd();
    this.squad.dispose();
    this.stadium.dispose();
    this.renderer.dispose();
  }

  private makeTrail() {
    const n = 18;
    const pos = new Float32Array(n * 2 * 3), fade = new Float32Array(n * 2);
    const geo = new THREE.BufferGeometry();
    const attr = new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage);
    const fadeAttr = new THREE.BufferAttribute(fade, 1).setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute("position", attr);
    geo.setAttribute("aFade", fadeAttr);
    const index: number[] = [];
    for (let i = 0; i < n - 1; i++) index.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
    geo.setIndex(index);
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      vertexShader: "attribute float aFade; varying float vF; void main(){ vF = aFade; gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.); }",
      fragmentShader: "varying float vF; void main(){ gl_FragColor = vec4(vec3(1., .95, .75) * vF * vF * .75, 1.); }",
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.frustumCulled = false;
    mesh.visible = false;
    this.scene.add(mesh);
    return { mesh, pos, at: 0, attr, fade, fadeAttr, x: new Float32Array(n), y: new Float32Array(n), z: new Float32Array(n), on: 0 };
  }

  private savePrev() {
    const s = this.s;
    for (let i = 0; i < 22; i++) {
      this.px[i] = s.players[i].x;
      this.pz[i] = s.players[i].z;
      this.pa[i] = s.players[i].air;
    }
    this.pb.set(s.ball.x, s.ball.y, s.ball.z);
  }

  private frame = (now: number) => {
    if (this.dead) return;
    this.raf = requestAnimationFrame(this.frame);
    const real = (now - this.last) / 1000;
    this.last = now;
    const dt = Math.min(real, 0.1);
    this.adaptDpr(real);
    if (!this.paused) {
      this.stadium.update(dt);
      if (this.replayF >= 0) this.playReplay(dt);
      else this.live(dt);
    }
    this.renderer.render(this.scene, this.camera);
    this.hudT -= dt;
    if (this.hudT <= 0) {
      this.hudT = 0.08;
      this.sendHud();
    }
  };

  private live(dt: number) {
    this.acc += dt;
    while (this.acc >= TICK) {
      this.acc -= TICK;
      this.tick();
      if (this.replayF >= 0) return;
    }
    this.draw(this.acc / TICK, dt);
  }

  private tick() {
    const s = this.s;
    this.savePrev();
    const inp: Input = { mx: this.stick.x, mz: -this.stick.y, sprint: this.sprint, press: this.press, contain: this.contain };
    this.press = null;
    stepMatch(s, inp);
    for (const e of s.ev) this.onEvent(e);
    this.moveOfficials();
    for (let i = 0; i < 22; i++) this.motion.update(i, s.players[i], s, TICK);
    for (let i = 0; i < 3; i++) this.motion.updateSimple(REFEREE + i, Math.sqrt(this.off.vx[i] ** 2 + this.off.vz[i] ** 2), TICK);
    this.record();
    if (s.phase === Phase.Goal && !this.replayed && s.phaseT >= REPLAY_AT) this.startReplay();
    if (s.phase !== Phase.Goal) this.replayed = false;
    if (s.phase === Phase.FullTime && !this.ended && s.phaseT > 330) {
      this.ended = true;
      this.hooks.onEnd({ home: s.teams[0].name, away: s.teams[1].name, g0: s.teams[0].goals, g1: s.teams[1].goals, s });
    }
    const box = Math.abs(s.ball.x) > HALF_L - 22 && Math.abs(s.ball.z) < 26;
    if (box !== this.tense) {
      this.tense = box;
      crowdTension(box);
    }
    if (s.tick % (HZ * 41) === 0) crowdChant();
  }

  private onEvent(e: MatchEvent) {
    const s = this.s;
    const you = s.user >= 0 ? s.players[s.user].team : 0;
    switch (e.t) {
      case "kick":
        this.lastKickTick = s.tick;
        playFreeKickSfx("kick");
        if (e.kind === Kick.Shot && e.speed > 21) this.trail.on = 40;
        break;
      case "post": case "bar":
        playFreeKickSfx("post");
        this.hooks.onMessage(e.t === "post" ? "Штанга!" : "Перекладина!");
        break;
      case "net": {
        const b = s.ball;
        this.stadium.netHit(b.x > 0 ? 1 : -1, b.y, b.z, Math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz) + 8);
        playFreeKickSfx("net");
        break;
      }
      case "goal":
        this.goalTick = s.tick;
        playFreeKickSfx(e.team === you ? "roar" : "groan");
        this.hooks.onMessage(e.long ? "ГОЛ! Дальний удар!" : e.kind === Kick.Header ? "ГОЛ! Головой!" : "ГОЛ!", true);
        crowdHush();
        break;
      case "save":
        this.hooks.onMessage(e.held ? "Вратарь забирает" : "Сейв!");
        break;
      case "miss":
        if (e.near) { playFreeKickSfx("groan"); this.hooks.onMessage("Рядом со штангой!"); }
        break;
      case "whistle":
        whistle(e.n);
        break;
      case "foul":
        whistle(1);
        break;
      case "offside":
        whistle(1);
        this.hooks.onMessage("Вне игры");
        break;
      case "out":
        if (e.set === "corner") this.hooks.onMessage("Угловой");
        else if (e.set === "penalty") this.hooks.onMessage("Пенальти!", true);
        else if (e.set === "free") this.hooks.onMessage("Штрафной");
        else if (e.set === "goalkick") this.hooks.onMessage("От ворот");
        else if (e.set === "throw") this.hooks.onMessage("Аут");
        break;
      case "feint":
        if (e.beat >= 0) this.hooks.onMessage("Красивый финт!");
        break;
      case "added":
        this.hooks.onMessage(`Добавлено ${Math.max(1, Math.round(e.seconds / 60))} мин`);
        break;
      default:
    }
  }

  private moveOfficials() {
    const b = this.s.ball, o = this.off;
    const team0 = this.s.players.slice(1, 11).map((p) => p.x).sort((a, c) => a - c);
    const team1 = this.s.players.slice(12, 22).map((p) => p.x).sort((a, c) => a - c);
    const goals = [
      [b.x - Math.sign(b.x || 1) * 11, b.z * 0.72 - Math.sign(b.z || 1) * 9],
      [Math.max(team1[team1.length - 1], b.x, 0), -HALF_W - 1.1],
      [Math.min(team0[0], b.x, 0), HALF_W + 1.1],
    ];
    goals.forEach(([tx, tz], i) => {
      const dx = tx - o.x[i], dz = tz - o.z[i];
      const d = Math.sqrt(dx * dx + dz * dz);
      const want = d < 1.2 ? 0 : Math.min(7, d * 0.75);
      const vx = d > 0.01 ? (dx / d) * want : 0, vz = d > 0.01 ? (dz / d) * want : 0;
      o.vx[i] += (vx - o.vx[i]) * 0.08;
      o.vz[i] += (vz - o.vz[i]) * 0.08;
      o.x[i] += o.vx[i] * TICK;
      o.z[i] += o.vz[i] * TICK;
    });
  }

  private place(i: number, x: number, y: number, z: number, yaw: number, a: number, b: number, w: number) {
    const dx = x - this.camera.position.x, dz = z - this.camera.position.z;
    this.squad.set(i, x, y, z, yaw, a, b, w, dx * dx + dz * dz < NEAR_LOD * NEAR_LOD);
  }

  private draw(alpha: number, dt: number) {
    const s = this.s;
    this.updateCamera(dt);
    for (let i = 0; i < 22; i++) {
      const p = s.players[i];
      const target = Math.atan2(p.hx, p.hz);
      if (this.motion.turning(i)) this.turned[i] = 1;
      else if (this.turned[i]) { this.turned[i] = 0; this.yaw[i] = target; }
      else this.yaw[i] += shortest(this.yaw[i], target) * damp(22, dt);
      const pose = this.motion.pose[i];
      this.place(i, this.px[i] + (p.x - this.px[i]) * alpha, this.pa[i] + (p.air - this.pa[i]) * alpha, this.pz[i] + (p.z - this.pz[i]) * alpha, this.yaw[i], pose.rowA, pose.rowB, pose.w);
    }
    for (let i = 0; i < 3; i++) {
      const o = this.off, v2 = o.vx[i] ** 2 + o.vz[i] ** 2;
      if (v2 > 0.2) this.yaw[REFEREE + i] += shortest(this.yaw[REFEREE + i], Math.atan2(o.vx[i], o.vz[i])) * damp(10, dt);
      else this.yaw[REFEREE + i] += shortest(this.yaw[REFEREE + i], Math.atan2(s.ball.x - o.x[i], s.ball.z - o.z[i])) * damp(6, dt);
      const pose = this.motion.pose[REFEREE + i];
      this.place(REFEREE + i, o.x[i], 0, o.z[i], this.yaw[REFEREE + i], pose.rowA, pose.rowB, pose.w);
    }
    this.squad.commit();
    const b = s.ball;
    const x = this.pb.x + (b.x - this.pb.x) * alpha, y = this.pb.y + (b.y - this.pb.y) * alpha, z = this.pb.z + (b.z - this.pb.z) * alpha;
    const held = b.owner >= 0 && (s.players[b.owner].act === Act.Hold || s.players[b.owner].act === Act.Catch);
    this.placeBall(x, Math.max(y, held ? 0.9 : BALL_R), z, b.vx, b.vz, dt);
    this.drawTrail(x, y, z, dt);
    this.drawMarkers(alpha, dt);
  }

  private placeBall(x: number, y: number, z: number, vx: number, vz: number, dt: number) {
    this.ball.position.set(x, y, z);
    const v = Math.sqrt(vx * vx + vz * vz);
    if (v > 0.1) {
      this.tmp.set(vz / v, 0, -vx / v);
      this.tmpQ.setFromAxisAngle(this.tmp, (v / BALL_R) * dt);
      this.spin.premultiply(this.tmpQ);
      this.ball.quaternion.copy(this.spin);
    }
    this.ballShadow.position.set(x - (SUN.x / SUN.y) * y, 0.02, z - (SUN.z / SUN.y) * y);
    const k = 1 / (1 + y * 0.12);
    this.ballShadow.scale.setScalar(1 + y * 0.05);
    (this.ballShadow.material as THREE.MeshBasicMaterial).opacity = 0.45 * k;
  }

  private drawTrail(x: number, y: number, z: number, dt: number) {
    const t = this.trail, n = t.x.length;
    t.on = Math.max(0, t.on - dt * 60);
    t.mesh.visible = t.on > 0;
    if (!t.mesh.visible) {
      t.x.fill(x); t.y.fill(y); t.z.fill(z);
      return;
    }
    for (let i = n - 1; i > 0; i--) { t.x[i] = t.x[i - 1]; t.y[i] = t.y[i - 1]; t.z[i] = t.z[i - 1]; }
    t.x[0] = x; t.y[0] = y; t.z[0] = z;
    const cam = this.camera.position;
    for (let i = 0; i < n; i++) {
      const j = Math.min(i + 1, n - 1), h = Math.max(i - 1, 0);
      let dx = t.x[h] - t.x[j], dy = t.y[h] - t.y[j], dz = t.z[h] - t.z[j];
      const vx = cam.x - t.x[i], vy = cam.y - t.y[i], vz = cam.z - t.z[i];
      const ox = dy * vz - dz * vy, oy = dz * vx - dx * vz, oz = dx * vy - dy * vx;
      const l = Math.sqrt(ox * ox + oy * oy + oz * oz) || 1;
      dx = ox / l; dy = oy / l; dz = oz / l;
      const f = 1 - i / n, w = BALL_R * 1.1 * f;
      t.pos.set([t.x[i] + dx * w, t.y[i] + dy * w, t.z[i] + dz * w, t.x[i] - dx * w, t.y[i] - dy * w, t.z[i] - dz * w], i * 6);
      t.fade[i * 2] = t.fade[i * 2 + 1] = f * Math.min(1, t.on / 12);
    }
    t.attr.needsUpdate = true;
    t.fadeAttr.needsUpdate = true;
  }

  private drawMarkers(alpha: number, dt: number) {
    const s = this.s;
    const show = s.user >= 0 && s.phase !== Phase.FullTime && s.phase !== Phase.Goal;
    this.marker.visible = show;
    this.arrow.visible = show;
    this.legs.visible = show;
    if (s.tick % 6 === 0) this.aimAt = show ? passTarget(s, this.stick.x, -this.stick.y) : -1;
    this.aim.visible = this.aimAt >= 0;
    if (this.aimAt >= 0) {
      const m = s.players[this.aimAt];
      this.aim.position.set(this.px[m.i] + (m.x - this.px[m.i]) * alpha, 0.03, this.pz[m.i] + (m.z - this.pz[m.i]) * alpha);
    }
    if (show) {
      const p = s.players[s.user];
      const x = this.px[p.i] + (p.x - this.px[p.i]) * alpha, z = this.pz[p.i] + (p.z - this.pz[p.i]) * alpha;
      const k = 1 + Math.sin(s.tick * 0.12) * 0.05;
      this.marker.position.set(x, 0.03, z);
      this.marker.scale.set(k, k, 1);
      this.arrow.position.set(x, 2.32 + Math.sin(s.tick * 0.09) * 0.06, z);
      this.arrow.rotation.y += dt * 2.4;
      this.legs.position.set(x, 2.1, z);
      this.legs.quaternion.copy(this.camera.quaternion);
      const far = Math.min(2, this.camera.position.distanceTo(this.legs.position) / 45);
      this.legs.scale.set(far, far, 1);
      this.legsFill.scale.set(Math.max(0.01, 1.12 * p.stamina), 0.09, 1);
      (this.legsFill.material as THREE.MeshBasicMaterial).color.set(p.stamina > 0.5 ? "#d6ff3f" : p.stamina > 0.25 ? "#fbbf24" : "#ef4444");
    }
    // Where a ball in the air comes down.
    const b = s.ball;
    let on = false;
    if (b.owner < 0 && b.y > 2.2) {
      const start = Math.max(0, Math.floor((s.tick - s.predFrom) / PRED_STEP));
      for (let i = start; i < s.predN; i++) {
        const y = s.pred[i * 3 + 1];
        if (y < 1.5) {
          this.landing.position.set(s.pred[i * 3], 0.03, s.pred[i * 3 + 2]);
          on = true;
          break;
        }
      }
    }
    this.landing.visible = on;
  }

  private updateCamera(dt: number) {
    const s = this.s, b = s.ball;
    const cam = this.camera;
    if (s.phase === Phase.Goal && s.lastGoal) {
      const c = s.players[s.lastGoal.p >= 0 ? s.lastGoal.p : 0];
      const dir = s.lastGoal.team === 0 ? 1 : -1;
      this.camPos.lerp(this.tmp.set(c.x - dir * 9, 2.6, c.z + 10), damp(1.8, dt));
      this.look.lerp(this.tmp.set(c.x, 1.3, c.z), damp(5, dt));
      this.fov += (19 - this.fov) * damp(2, dt);
    } else {
      // Ahead of the play, more so the faster it goes.
      const ownerV = b.owner >= 0 ? s.players[b.owner] : null;
      const vx = ownerV ? ownerV.vx : b.vx, vz = ownerV ? ownerV.vz : b.vz;
      const lead = Math.max(-9, Math.min(9, vx * 0.75));
      let fx = b.x + lead;
      let fz = b.z + Math.max(-4, Math.min(4, vz * 0.4));
      const set = s.set;
      if (set && (set.kind === "corner" || set.kind === "penalty")) {
        fx = Math.sign(set.x || 1) * (HALF_L - 13);
        fz = set.z * 0.35;
      }
      this.focus.x += (fx - this.focus.x) * damp(2.6, dt);
      this.focus.z += (fz - this.focus.z) * damp(2, dt);
      const nearGoal = Math.max(0, Math.min(1, (Math.abs(this.focus.x) - 26) / 16));
      const wide = Math.abs(this.focus.x) / HALF_L;
      const tx = Math.max(-46, Math.min(46, this.focus.x * 0.94));
      const pushIn = 57 - nearGoal * 6;
      const tz = pushIn + this.focus.z * 0.14;
      const ty = 20.5 - nearGoal * 2.5;
      this.camPos.x += (tx - this.camPos.x) * damp(3, dt);
      this.camPos.y += (ty - this.camPos.y) * damp(1.6, dt);
      this.camPos.z += (tz - this.camPos.z) * damp(1.6, dt);
      this.look.lerp(this.tmp.set(this.focus.x, 1, this.focus.z * 0.62), damp(6, dt));
      const want = 23 - wide * 1.5;
      this.fov += (want - this.fov) * damp(2, dt);
    }
    cam.position.copy(this.camPos);
    cam.lookAt(this.look);
    if (Math.abs(cam.fov - this.fov) > 0.01) {
      cam.fov = this.fov;
      cam.updateProjectionMatrix();
    }
  }

  // --- the replay ---------------------------------------------------------------------------------

  private record() {
    const s = this.s;
    const at = (s.tick % RING) * REC;
    const r = this.ring;
    r[at] = s.ball.x; r[at + 1] = s.ball.y; r[at + 2] = s.ball.z;
    for (let i = 0; i < PEOPLE; i++) {
      const k = at + 3 + i * 7;
      const pose = this.motion.pose[i];
      if (i < 22) {
        const p = s.players[i];
        r[k] = p.x; r[k + 1] = p.air; r[k + 2] = p.z;
        r[k + 3] = Math.atan2(p.hx, p.hz);
      } else {
        r[k] = this.off.x[i - 22]; r[k + 1] = 0; r[k + 2] = this.off.z[i - 22]; r[k + 3] = this.yaw[i];
      }
      r[k + 4] = pose.rowA; r[k + 5] = pose.rowB; r[k + 6] = pose.w;
    }
    this.ringTick = s.tick;
  }

  private startReplay() {
    this.replayed = true;
    if (this.goalTick < 0 || this.demo) return;
    const oldest = this.ringTick - RING + 2;
    this.replayF = Math.max(oldest, Math.min(this.goalTick - 150, this.lastKickTick - 70));
    this.replayEnd = this.goalTick + 36;
    const s = this.s;
    const dir = s.ball.x > 0 ? 1 : -1;
    this.camPos.set(dir * (HALF_L + 12), 3.8, s.ball.z * 0.5 + 3);
    this.fov = 19;
    this.look.set(s.ball.x, 1, s.ball.z);
    this.sendHud();
  }

  private endReplay() {
    this.replayF = -1;
    this.last = performance.now();
    const s = this.s;
    const c = s.players[s.lastGoal && s.lastGoal.p >= 0 ? s.lastGoal.p : 0];
    this.camPos.set(c.x - Math.sign(c.x || 1) * 9, 2.6, c.z + 10);
    this.look.set(c.x, 1.3, c.z);
    this.sendHud();
  }

  private playReplay(dt: number) {
    this.replayF += dt * HZ * REPLAY_RATE;
    if (this.replayF >= this.replayEnd) {
      this.endReplay();
      return;
    }
    const f0 = Math.floor(this.replayF), t = this.replayF - f0;
    const a = (f0 % RING) * REC, c = ((f0 + 1) % RING) * REC;
    const r = this.ring;
    const bx = r[a] + (r[c] - r[a]) * t, by = r[a + 1] + (r[c + 1] - r[a + 1]) * t, bz = r[a + 2] + (r[c + 2] - r[a + 2]) * t;
    this.look.lerp(this.tmp.set(bx, by * 0.7 + 0.4, bz), damp(7, dt));
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.look);
    this.camera.fov = this.fov;
    this.camera.updateProjectionMatrix();
    for (let i = 0; i < PEOPLE; i++) {
      const k = a + 3 + i * 7, q = c + 3 + i * 7;
      const yaw = r[k + 3] + shortest(r[k + 3], r[q + 3]) * t;
      this.place(i, r[k] + (r[q] - r[k]) * t, r[k + 1] + (r[q + 1] - r[k + 1]) * t, r[k + 2] + (r[q + 2] - r[k + 2]) * t, yaw, r[k + 4], r[k + 5], r[k + 6]);
    }
    this.squad.commit();
    this.placeBall(bx, Math.max(by, BALL_R), bz, (r[c] - r[a]) * HZ, (r[c + 2] - r[a + 2]) * HZ, dt * REPLAY_RATE);
    this.drawTrail(bx, by, bz, dt);
    this.marker.visible = false;
    this.arrow.visible = false;
    this.aim.visible = false;
    this.legs.visible = false;
    this.landing.visible = false;
  }

  // --- housekeeping -------------------------------------------------------------------------------

  private sendHud() {
    const s = this.s;
    const u = s.user >= 0 ? s.players[s.user] : null;
    const set = s.set;
    const taking = !!(u && set && set.taker === u.i);
    const hud: Hud = {
      g0: s.teams[0].goals, g1: s.teams[1].goals, clock: clockText(s),
      attack: !!(u && (s.ball.owner === u.i || taking)),
      setKind: taking ? set!.kind : null,
      keeper: !!(u && u.role === "GK" && (s.ball.owner === u.i || taking)),
      chipHere: !!u && !set && u.x * (u.team === 0 ? 1 : -1) > HALF_L - 26 && Math.abs(u.z) < 16,
      replay: this.replayF >= 0,
      ended: s.phase === Phase.FullTime,
    };
    const key = JSON.stringify(hud);
    if (key !== this.hudKey) {
      this.hudKey = key;
      this.hooks.onHud(hud);
    }
  }

  private adaptDpr(real: number) {
    this.frameN += 1;
    this.frameSum += real;
    if (this.frameN < FPS_SAMPLE) return;
    const avg = this.frameSum / this.frameN;
    this.frameN = 0;
    this.frameSum = 0;
    const cap = Math.min(window.devicePixelRatio || 1, DPR_MAX);
    let next = this.dpr;
    if (avg > 0.0215) next = Math.max(DPR_MIN, this.dpr - 0.2);
    else if (avg < 0.0172 && this.dpr < cap) next = Math.min(cap, this.dpr + 0.05);
    if (next !== this.dpr) {
      this.dpr = next;
      this.renderer.setPixelRatio(next);
      this.renderer.setSize(this.width, this.height, false);
    }
  }
}
