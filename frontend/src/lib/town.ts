/** «Город»: the player's own football town — an overview map of six
 * districts and one illustrated scene per district (src/assets/town/*.webp,
 * 900×1200) with tap zones over its buildings and a light animated layer of
 * residents and vehicles walking fixed routes. Visual only for now: buying
 * houses and residents comes later, on the backend. Every coordinate here is
 * in the picture's own pixels (900×1200). */

import beachArt from "@/assets/town/beach.webp";
import businessArt from "@/assets/town/business.webp";
import centerArt from "@/assets/town/center.webp";
import favelaArt from "@/assets/town/favela.webp";
import mapArt from "@/assets/town/map.webp";
import mountainsArt from "@/assets/town/mountains.webp";

export const SCENE_W = 900;
export const SCENE_H = 1200;

export type Pt = [x: number, y: number];
export type Box = [x0: number, y0: number, x1: number, y1: number];

export type TownBuilding = { code: string; name: string; emoji: string; about: string; zone: Box };

/** A route a sprite follows: `loop` goes round a closed polygon, otherwise
 * it walks to the end and back. */
export type Route = { points: Pt[]; loop?: boolean };

export type Mover = {
  sprite: string; // "people/03", "vehicles/01"
  route: Route;
  /** Units per second, in picture pixels. */
  speed: number;
  /** Where on the route it starts, 0…1 of its length. */
  start: number;
};

export type DistrictCode = "center" | "favela" | "beach" | "mountains" | "business";

export type District = {
  code: DistrictCode;
  name: string;
  emoji: string;
  tagline: string;
  art: string;
  buildings: TownBuilding[];
  movers: Mover[];
  /** Water strip that shimmers, if any. */
  water?: Box;
};

/** Sprite sizes (px of the cut-out file) — the picture keeps its own aspect. */
export const SPRITES: Record<string, { w: number; h: number; height: number; facesRight: boolean }> = {
  ...Object.fromEntries(
    [64, 59, 78, 76, 88, 79, 64, 55, 75, 53, 70, 65].map((w, i) => [
      `people/${String(i + 1).padStart(2, "0")}`, { w, h: 128, height: 46, facesRight: true },
    ]),
  ),
  "vehicles/01": { w: 131, h: 160, height: 84, facesRight: false }, // tram
  "vehicles/02": { w: 198, h: 160, height: 76, facesRight: false }, // monorail
  "vehicles/03": { w: 168, h: 160, height: 68, facesRight: false }, // bus
  "vehicles/04": { w: 172, h: 160, height: 60, facesRight: false }, // van
  "vehicles/05": { w: 183, h: 160, height: 50, facesRight: false }, // hatchback
  "vehicles/06": { w: 141, h: 160, height: 42, facesRight: false }, // scooter
  "vehicles/07": { w: 121, h: 160, height: 46, facesRight: false }, // ice cream cart
  "vehicles/08": { w: 184, h: 160, height: 50, facesRight: false }, // beach buggy
};

const b = (code: string, name: string, emoji: string, about: string, zone: Box): TownBuilding => ({ code, name, emoji, about, zone });
const walk = (sprite: number, points: Pt[], start: number, speed = 10, loop = false): Mover => ({
  sprite: `people/${String(sprite).padStart(2, "0")}`, route: { points, loop }, speed, start,
});
const drive = (sprite: number, points: Pt[], start: number, speed = 45, loop = false): Mover => ({
  sprite: `vehicles/${String(sprite).padStart(2, "0")}`, route: { points, loop }, speed, start,
});

/** An ellipse as a closed polygon. */
function ring(cx: number, cy: number, rx: number, ry: number, n = 24): Pt[] {
  return Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2;
    return [Math.round(cx + rx * Math.cos(a)), Math.round(cy + ry * Math.sin(a))] as Pt;
  });
}

const CENTER_PROMENADE: Pt[] = [[20, 965], [450, 1028], [880, 1090]];
const PLAZA = ring(450, 545, 170, 112);
/** The street round the plaza, the only road the car drives. */
const CENTER_ROAD: Pt[] = [[300, 335], [450, 328], [615, 340], [640, 420], [642, 600], [625, 690], [450, 708], [295, 698], [282, 600], [282, 420]];

const FAVELA_PROMENADE: Pt[] = [[10, 995], [450, 1012], [890, 1040]];
const BEACH_PROMENADE: Pt[] = [[10, 545], [300, 505], [560, 472], [700, 456]];
const SHORE: Pt[] = [[60, 990], [450, 968], [850, 915]];
const BEACH_COURT: Pt[] = [[245, 625], [615, 625], [615, 915], [245, 915]];
const BUSINESS_AVENUE: Pt[] = [[10, 990], [450, 1005], [890, 1020]];

const DRAWN: District[] = [
  {
    code: "center",
    name: "Центр",
    emoji: "🏛️",
    tagline: "Площадь с фонтаном, ратуша и музей футбола",
    art: centerArt,
    water: [0, 1070, 900, 1200],
    buildings: [
      b("town_hall", "Ратуша", "🏛️", "Сердце города с часовой башней.", [100, 30, 310, 250]),
      b("museum", "Музей футбола", "🏆", "Кубки, футболки и мячи великих матчей.", [320, 140, 530, 280]),
      b("hotel_tower", "Отель «Башня»", "🏨", "Стеклянная башня с видом на площадь.", [530, 50, 670, 300]),
      b("market", "Крытый рынок", "🧺", "Свежие фрукты и овощи под стеклянной крышей.", [660, 120, 890, 300]),
      b("cinema", "Кинотеатр", "🎬", "Премьеры и показы великих финалов.", [35, 280, 215, 450]),
      b("barber", "Барбершоп", "💈", "Стрижка как у звезды перед матчем.", [680, 345, 865, 490]),
      b("sports_bar", "Спорт-бар", "📺", "Большой экран и все матчи тура.", [25, 485, 250, 650]),
      b("bakery", "Пекарня", "🥐", "Утренний кофе и круассаны на террасе.", [665, 515, 870, 700]),
      b("bank", "Банк", "🏦", "Колонны, мрамор и надёжные вклады.", [20, 675, 250, 900]),
      b("boot_shop", "Бутсы", "👟", "Магазин бутс на любой газон.", [250, 720, 440, 905]),
      b("newspaper", "Редакция газеты", "📰", "Здесь печатают спортивные новости города.", [440, 725, 640, 905]),
      b("apartments", "Жилой дом", "🏢", "Квартиры с балконами у самой площади.", [665, 735, 865, 945]),
    ],
    movers: [
      drive(5, CENTER_ROAD, 0, 24, true),
      walk(1, PLAZA, 0.1, 8, true),
      walk(4, PLAZA, 0.55, 7, true),
      walk(10, CENTER_PROMENADE, 0.2),
      walk(11, CENTER_PROMENADE, 0.7, 11),
      walk(3, [[300, 305], [450, 300], [620, 310]], 0.3, 6),
      walk(12, [[268, 320], [270, 500], [275, 700]], 0.6),
      walk(9, [[270, 715], [450, 712], [650, 715]], 0.1, 9),
    ],
  },
  {
    code: "favela",
    name: "Фавелы",
    emoji: "🎶",
    tagline: "Яркие дома на холме и корт, где рождаются звёзды",
    art: favelaArt,
    water: [0, 1060, 900, 1200],
    buildings: [
      b("church", "Церковь", "⛪", "Белая церковь с колоколом над склоном.", [30, 30, 215, 290]),
      b("community", "Общинный центр", "📚", "Книги, кружки и уроки для детей района.", [275, 145, 495, 300]),
      b("guesthouse", "Гостевой дом", "🌺", "Самый высокий дом с видом на залив.", [510, 15, 705, 235]),
      b("boxing", "Боксёрский зал", "🥊", "Груши, ринг и характер.", [675, 205, 890, 370]),
      b("samba", "Самба-клуб", "🥁", "Барабаны слышно на весь холм.", [20, 335, 270, 510]),
      b("barber", "Барбершоп", "💈", "Самые модные причёски района.", [665, 370, 890, 530]),
      b("bar", "Угловой бар", "🍹", "Свежие соки и разговоры о футболе.", [20, 545, 260, 735]),
      b("street_food", "Уличная еда", "🌽", "Гриль, пастели и сладкая кукуруза.", [685, 580, 895, 735]),
      b("studio", "Музыкальная студия", "🎸", "Здесь пишут гимны болельщиков.", [5, 750, 215, 975]),
      b("mural", "Дом с муралом", "🎨", "Стены расписаны художниками района.", [245, 745, 445, 985]),
      b("shop", "Лавка", "🍉", "Фрукты, вода и всё для дома.", [460, 750, 640, 980]),
      b("garden", "Дом с садом", "🌿", "Огород и цветы прямо на крыше.", [680, 755, 895, 1000]),
    ],
    movers: [
      walk(7, FAVELA_PROMENADE, 0.1, 9),
      walk(5, FAVELA_PROMENADE, 0.8, 6),
      walk(1, [[300, 690], [600, 690]], 0.2, 11),
      walk(2, [[300, 480], [295, 690]], 0.5),
      walk(8, [[605, 480], [610, 690]], 0.1, 12),
      walk(4, [[250, 735], [450, 738], [660, 735]], 0.6, 7),
      walk(3, [[220, 305], [480, 310]], 0.3, 5),
    ],
  },
  {
    code: "beach",
    name: "Пляж",
    emoji: "🏖️",
    tagline: "Променад, пляжный футбол и виллы у океана",
    art: beachArt,
    water: [0, 1000, 900, 1200],
    buildings: [
      b("white_villa", "Белая вилла", "🏡", "Своя терраса и бассейн у моря.", [40, 80, 240, 300]),
      b("pink_villa", "Розовая вилла", "🌸", "Балконы в цветах бугенвиллеи.", [260, 95, 450, 280]),
      b("hotel", "Бутик-отель", "🏨", "Арки, цветы и вид на закат.", [455, 50, 670, 280]),
      b("penthouse", "Пентхаус", "🌇", "Самая дорогая крыша на побережье.", [690, 10, 870, 230]),
      b("surf", "Серф-школа", "🏄", "Доски напрокат и уроки на волне.", [20, 335, 215, 500]),
      b("seafood", "Рыбный ресторан", "🦐", "Улов дня на гриле.", [215, 330, 470, 470]),
      b("ice_cream", "Мороженое", "🍦", "Розовый киоск, к которому очередь всё лето.", [490, 320, 650, 460]),
      b("lighthouse", "Маяк", "🗼", "Красно-белый маяк на скалах.", [740, 240, 880, 450]),
      b("yacht_club", "Яхт-клуб", "⛵", "Пирс, яхты и морские прогулки.", [610, 510, 840, 650]),
      b("beach_bar", "Бар на сваях", "🍸", "Коктейли с видом на пляжный матч.", [5, 575, 225, 790]),
      b("volley", "Пляжная хижина", "🏐", "Мячи, сетки и всё для игры на песке.", [45, 805, 205, 945]),
      b("coconut", "Кокосы", "🥥", "Свежий кокос после матча.", [645, 790, 820, 935]),
    ],
    movers: [
      walk(6, SHORE, 0.1, 8),
      walk(2, BEACH_PROMENADE, 0.7, 9),
      walk(8, BEACH_COURT, 0, 12, true),
      walk(1, BEACH_COURT, 0.5, 10, true),
      walk(11, [[640, 650], [850, 745]], 0.3, 6),
    ],
  },
  {
    code: "mountains",
    name: "Горы",
    emoji: "🏔️",
    tagline: "Шале, канатная дорога и поле над озером",
    art: mountainsArt,
    water: [0, 1040, 900, 1200],
    buildings: [
      b("chalet", "Большое шале", "🏔️", "Дерево, камин и цветы на балконах.", [45, 60, 320, 230]),
      b("hut", "Горная хижина", "🛖", "Приют для тех, кто дошёл до вершины.", [400, 100, 515, 170]),
      b("spa", "Спа-отель", "♨️", "Тёплый бассейн с видом на горы.", [15, 245, 420, 460]),
      b("cable_car", "Канатная дорога", "🚡", "Станция кабинок на вершину.", [495, 295, 720, 400]),
      b("observatory", "Обсерватория", "🔭", "Купол и телескоп над облаками.", [720, 160, 885, 280]),
      b("glass_villa", "Стеклянная вилла", "🪟", "Дом над обрывом и водопадом.", [640, 405, 890, 530]),
      b("guesthouse", "Каменный дом", "🌼", "Старый гостевой дом у поля.", [30, 490, 245, 660]),
      b("cabin", "Бревенчатый домик", "🪵", "Маленький домик у водопада.", [625, 550, 770, 650]),
      b("dairy", "Сыроварня", "🧀", "Горные сыры по старому рецепту.", [15, 680, 290, 845]),
      b("farm", "Ферма", "🌻", "Красный амбар, сено и подсолнухи.", [615, 685, 785, 790]),
      b("restaurant", "Ресторан у озера", "🍽️", "Ужин на террасе над водой.", [100, 830, 450, 1000]),
      b("fishing", "Рыбацкий дом", "🎣", "Пирс, лодка и тишина.", [600, 850, 870, 1030]),
    ],
    movers: [
      walk(9, [[60, 1005], [300, 1020], [560, 1000]], 0.2, 8),
      walk(4, [[60, 1005], [300, 1020], [560, 1000]], 0.75, 5),
      walk(8, [[280, 530], [600, 530]], 0.4, 12),
      walk(12, [[270, 700], [610, 700]], 0.1, 9),
      walk(3, [[590, 1000], [860, 985]], 0.6, 5),
    ],
  },
  {
    code: "business",
    name: "Бизнес-район",
    emoji: "💼",
    tagline: "Биржа, агенты, спонсоры и монорельс",
    art: businessArt,
    buildings: [
      b("hotel", "Гранд-отель", "🏨", "Классика для деловых гостей.", [70, 40, 255, 245]),
      b("twist", "Витая башня", "🌀", "Самый узнаваемый небоскрёб города.", [310, 10, 460, 300]),
      b("tv_tower", "Телебашня", "📡", "Отсюда транслируют матчи.", [500, 10, 610, 290]),
      b("sky_office", "Офис с садом", "🌳", "Сад на крыше и переговорные в зелени.", [675, 50, 890, 250]),
      b("tower", "Офисная башня", "🏙️", "Стекло, свет и деловые этажи.", [55, 270, 195, 520]),
      b("bank_tower", "Банк", "🚁", "Вертолётная площадка на крыше.", [690, 270, 865, 530]),
      b("law", "Юристы", "⚖️", "Контракты и трансферы под защитой.", [25, 530, 240, 710]),
      b("sponsors", "Офис спонсоров", "⚽", "Поле прямо на крыше.", [280, 410, 600, 660]),
      b("agents", "Футбольные агенты", "🤝", "Здесь договариваются о переходах.", [670, 545, 880, 720]),
      b("exchange", "Биржа", "📈", "Графики, сделки и большие деньги.", [20, 720, 285, 960]),
      b("cars", "Автосалон", "🏎️", "Спорткары за стеклом.", [310, 770, 560, 970]),
      b("congress", "Конгресс-центр", "🎤", "Презентации, форумы и жеребьёвки.", [580, 760, 895, 970]),
    ],
    movers: [
      walk(11, BUSINESS_AVENUE, 0.15, 10),
      walk(10, BUSINESS_AVENUE, 0.6, 8),
      walk(11, [[300, 700], [450, 720], [620, 740]], 0.4, 9),
      walk(8, [[80, 1090], [280, 1100], [340, 1150]], 0.2, 11),
      walk(9, [[255, 520], [265, 700], [280, 760]], 0.7, 8),
    ],
  },
];

/** A livelier street: every resident gets a neighbour on the same route,
 * half a lap behind, looking different. */
function crowd(movers: Mover[]): Mover[] {
  const extra = movers
    .filter((m) => m.sprite.startsWith("people/"))
    .map((m, i) => ({
      ...m,
      sprite: `people/${String(((Number(m.sprite.slice(7)) + 4 + i) % 12) + 1).padStart(2, "0")}`,
      start: (m.start + 0.5) % 1,
      speed: m.speed * 0.85,
    }));
  return [...movers, ...extra];
}

export const DISTRICTS: District[] = DRAWN.map((d) => ({ ...d, movers: crowd(d.movers) }));

export type MapZone = { code: DistrictCode | "base"; name: string; emoji: string; zone: Box };

export const TOWN_MAP = mapArt;

/** The overview map: each district's area on it; the club base opens its own page. */
export const MAP_ZONES: MapZone[] = [
  { code: "mountains", name: "Горы", emoji: "🏔️", zone: [20, 90, 440, 420] },
  { code: "business", name: "Бизнес-район", emoji: "💼", zone: [450, 80, 890, 390] },
  { code: "favela", name: "Фавелы", emoji: "🎶", zone: [20, 460, 440, 730] },
  { code: "base", name: "Клубная база", emoji: "🏟️", zone: [450, 400, 890, 720] },
  { code: "beach", name: "Пляж", emoji: "🏖️", zone: [10, 740, 440, 1150] },
  { code: "center", name: "Центр", emoji: "🏛️", zone: [450, 740, 890, 1050] },
];

export const districtOf = (code: string | undefined): District | undefined => DISTRICTS.find((d) => d.code === code);

function segments(route: Route): Array<[Pt, Pt, number]> {
  const pts = route.loop ? [...route.points, route.points[0]] : route.points;
  const out: Array<[Pt, Pt, number]> = [];
  for (let i = 1; i < pts.length; i++) {
    const [a, c] = [pts[i - 1], pts[i]];
    out.push([a, c, Math.hypot(c[0] - a[0], c[1] - a[1])]);
  }
  return out;
}

export function routeLength(route: Route): number {
  return segments(route).reduce((sum, [, , len]) => sum + len, 0);
}

/** Where a mover is after `seconds`: its point and the way it moves
 * (dx > 0 — to the right). A loop goes round; an open route goes to the
 * end and back. */
export function moverAt(mover: Mover, seconds: number): { x: number; y: number; dx: number } {
  const segs = segments(mover.route);
  const total = segs.reduce((sum, [, , len]) => sum + len, 0);
  if (total === 0) {
    const [x, y] = mover.route.points[0];
    return { x, y, dx: 1 };
  }
  const travelled = mover.start * total + seconds * mover.speed;
  let d: number;
  let back = false;
  if (mover.route.loop) {
    d = ((travelled % total) + total) % total;
  } else {
    const period = total * 2;
    const p = ((travelled % period) + period) % period;
    back = p > total;
    d = back ? period - p : p;
  }
  for (const [a, c, len] of segs) {
    if (d <= len || len === 0) {
      const t = len === 0 ? 0 : d / len;
      const dx = (c[0] - a[0]) * (back ? -1 : 1);
      return { x: a[0] + (c[0] - a[0]) * t, y: a[1] + (c[1] - a[1]) * t, dx };
    }
    d -= len;
  }
  const last = segs[segs.length - 1][1];
  return { x: last[0], y: last[1], dx: 1 };
}

export type DecorCode = "pier" | "park" | "island";
export type DecorZone = { code: DecorCode; name: string; emoji: string; about: string; zone: Box };

/** Closed places on the overview map (backend town_service.DECOR — the codes
 * must match): dimmed with a lock until bought, then lit up. A drawn picture
 * (assets/town/decor/<code>.webp, transparent) replaces the emoji when it exists. */
export const DECOR_ZONES: DecorZone[] = [
  { code: "park", name: "Парк с фонтаном", emoji: "⛲", about: "Парк у горного озера: фонтан, фонари и скамейки для жителей", zone: [140, 360, 330, 465] },
  { code: "pier", name: "Пирс с колесом обозрения", emoji: "🎡", about: "Пирс в море с колесом обозрения и огнями над водой", zone: [455, 1062, 630, 1188] },
  { code: "island", name: "Остров легенды", emoji: "🏆", about: "Остров со статуей легенды клуба — виден с любого берега", zone: [655, 1062, 885, 1188] },
];

/** Where the fireworks go up once every place is open (over the stadium). */
export const FIREWORKS_BOX: Box = [480, 330, 880, 600];

export type Sky = "dawn" | "day" | "dusk" | "night";

/** The town's light by the player's own clock: dawn 6–8, day 8–18, dusk 18–21, night 21–6. */
export function skyAt(hour: number): Sky {
  if (hour >= 21 || hour < 6) return "night";
  if (hour < 8) return "dawn";
  if (hour >= 18) return "dusk";
  return "day";
}
