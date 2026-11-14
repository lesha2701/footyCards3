# «Мяч и Магия» — промпты для графики

Пока картинок нет, игра рисует встроенную SVG-графику. Положи PNG с нужным именем в
`frontend/public/magic/…`, и игра подхватит её вместо SVG. Код при этом менять не нужно:
достаточно отметить файл в `frontend/src/components/magic/art/pngArt.ts`.

Карта каждый раз генерируется заново, поэтому одной большой картинки карты нет. Она
собирается из кусочков: земля, лес, горы, вода, объекты. Каждый кусочек рисуется
отдельной картинкой.

## Общие правила для всех картинок

- **PNG с прозрачным фоном** (transparent background), без рамок, без текста, без логотипов.
- Один стиль на всё: держи «общий стиль» ниже в начале каждого промпта.
- **Всё оригинальное.** Не пиши в промптах названия чужих игр и студий.
- Свет сверху-слева. Тень под предметом не рисуй, её дорисует игра.
- Если генератор не умеет прозрачный фон, проси «on a plain flat white background», а фон потом
  уберёшь (например, remove.bg).

**Общий стиль** (вставляй в начало каждого промпта):

> stylized 2.5D game art, hand-painted look with soft 3D volume, chunky readable shapes, saturated
> juicy colors, soft rim light, clean dark outline, top-left lighting, mobile strategy game asset,
> high detail but readable at small size, isolated on transparent background, no text, no frame

## 1. Существа (14 шт.) — в полный рост

- Размер **1024×1024**.
- Существо стоит целиком, ноги внизу кадра, вокруг немного воздуха.
- Поза три четверти, **смотрит вправо**: игра сама отражает врагов, они смотрят влево.
- Внизу картинки игра накладывает полоску с фото футболиста и числом бойцов. Поэтому важное
  (голова, оружие) держи в верхних ~80%.
- Файлы: `frontend/public/magic/creatures/<код>.png`.

Добавка к промпту: `full body character, three-quarter view facing right, standing pose, whole
figure in frame with small margin, feet at the bottom`

### Орден Рассвета
Светлая раса: золото, белый, небесно-голубой, солнечные символы, лёгкие футбольные детали
(полосатые шарфы, мяч на гербе).

| Код | Промпт (после общего стиля) |
|---|---|
| `dawn_banner` | sturdy young soldier in white and gold armor holding a big tower shield with a sun emblem and a tall striped banner, determined smile, tier 1 common unit |
| `dawn_spear` | agile light javelin thrower in sky-blue tunic and gold trim, quiver of spears on the back, mid-throw pose, football scarf, tier 2 unit |
| `dawn_priest` | kind elderly sun priest in flowing white and gold robes, glowing sun staff, warm healing light around hands, tier 3 unit |
| `dawn_guard` | tall armored winged guardian with large white feathered wings, gold plate armor, halberd, heroic stance, tier 4 elite unit |
| `dawn_phoenix` | majestic blazing phoenix bird made of golden-orange fire, wings spread wide, sparks and light rays, legendary tier 5 creature |

### Легион Пепла
Тёмная раса: углисто-красный, фиолетовый, пепельно-серый, светящиеся глаза, огонь и тлеющие угли.

| Код | Промпт |
|---|---|
| `ash_bones` | cheeky skeleton football ultras fan with a torn red scarf and a wooden club, glowing red eyes, tier 1 common unit |
| `ash_imp` | small mischievous horned red imp throwing a fireball, bat-like tiny wings, grinning, tier 2 unit |
| `ash_witch` | ash witch in a tattered purple dress and pointy hat, stirring purple curse smoke from a ladle, green glowing eyes, tier 3 unit |
| `ash_golem` | heavy hulking stone golem with glowing lava cracks, ember eyes, massive fists, tier 4 elite unit |
| `ash_dragon` | dark abyss dragon with purple-black scales, ember breath, glowing orange eyes, wings half open, legendary tier 5 creature |

### Нейтральные монстры лагерей
Земляные и зелёные тона, задиристые и немного смешные.

| Код | Промпт |
|---|---|
| `wild_thug` | burly street brawler with tape-wrapped fists, sleeveless shirt, bald head, tough grin, tier 1 monster |
| `wild_sling` | scrappy hooligan kid with a cap and a slingshot, mid-shot pose, tier 2 monster |
| `wild_troll` | big mossy green troll stadium mascot beating a big drum, tusks, friendly-scary, tier 3 monster |
| `wild_ogre` | huge ogre carrying a bent goalpost as a club, leather straps, angry face, tier 4 monster |

## 2. Объекты карты — изометрия

- Размер **512×512**.
- Изометрический ракурс: «2:1 isometric view, seen from above at 30 degrees».
- Предмет стоит в центре **нижней половины** кадра, его основание — ромб примерно в половину
  ширины картинки.
- Файлы: `frontend/public/magic/objects/<имя>.png`.

Добавка: `isometric 2:1 game object, centered, standing on an invisible diamond tile`

| Имя файла | Промпт |
|---|---|
| `chest.png` | wooden treasure chest bound with gold, slightly open with gold coins glinting |
| `chest_taken.png` | the same treasure chest opened and empty |
| `well.png` | magical stone mana well with glowing blue water and floating sparkles |
| `tribune.png` | small wooden football fan stand with colorful flags and scarves |
| `reinforce.png` | army recruitment camp: banner on a pole and a supply crate with spears |
| `market.png` | colorful transfer market tent stall with a scale and contract scrolls |
| `mine.png` | small gold mine entrance in a rock with a wooden frame and a cart full of gold |
| `camp_1.png` | small monster camp: two ragged tents, a campfire, a club stuck in the ground |
| `camp_2.png` | bigger monster camp with three tents, campfire, skull totem |
| `camp_3.png` | fortified monster camp with spiked palisade, red flags, big skull totem, menacing |
| `camp_taken.png` | conquered camp: extinguished campfire, a white flag planted |
| `artifact_boots.png` | golden football boots on a stone pedestal, magical glow |
| `artifact_armband.png` | captain's armband on a stone pedestal, magical glow |
| `artifact_shinguards.png` | enchanted shin guards on a stone pedestal, magical glow |
| `artifact_whistle.png` | silver referee whistle on a stone pedestal, magical glow |
| `artifact_flag.png` | supporters' flag on a stone pedestal, magical glow |
| `castle_dawn.png` | white stone castle with gold roofs and sun flags, towers |
| `castle_ash.png` | dark basalt fortress with glowing ember windows and spikes |
| `castle_stadium.png` | castle fused with a football stadium, floodlights, stands |
| `castle_ice.png` | ice palace of glowing blue crystal |
| `castle_volcano.png` | fortress on a lava rock with molten streams |

### Герои на карте (512×512, изометрия, смотрит вправо)

| Имя файла | Промпт |
|---|---|
| `hero_dawn.png` | mounted hero knight on a white horse holding a sun banner, gold and sky-blue armor |
| `hero_ash.png` | mounted dark hero on a black horse with an ember banner, crimson and purple armor |
| `hero_gold.png` | gilded captain on a horse with a laurel wreath, golden armor |
| `hero_shadow.png` | hooded dark mage riding a black steed, violet magical glow |
| `hero_frost.png` | ice knight in pale-blue crystal armor riding a white horse |

## 3. Местность — 4 мира

Миры: `meadow` (луг), `desert` (пустыня), `snow` (снега), `ash` (пепельные земли).

**Земля.** Бесшовная изометрическая плитка, размер **512×256**, ромб 2:1 во весь кадр, по
3 варианта на мир. Файлы `frontend/public/magic/terrain/<мир>_ground_<1..3>.png`.

Промпт: `seamless isometric 2:1 diamond ground tile, top-down 30 degrees, <описание>, no objects, edges blend seamlessly`

- meadow: `lush green grass with tiny flowers and soft light patches`
- desert: `warm golden sand with small ripples and pebbles`
- snow: `fresh white snow with soft blue shadows and ice sparkles`
- ash: `dark ash ground with glowing ember cracks and grey dust`

**Дорога** (`<мир>_road.png`, 512×256): `seamless isometric 2:1 diamond tile of a dirt / sandstone
/ icy / basalt cobble road crossing the tile`.

**Препятствия** (512×512, изометрия, по 3 варианта): файлы `<мир>_tree_<1..3>.png`,
`<мир>_rock_<1..3>.png`, `<мир>_mountain_<1..3>.png`.

| Мир | Деревья | Камни | Горы |
|---|---|---|---|
| meadow | round lush oak tree | grey mossy boulder | green-grey mountain with a snow cap |
| desert | palm tree / tall cactus | sandstone rock | flat-topped mesa butte |
| snow | snowy pine tree | ice-covered rock | white snowy peak |
| ash | charred dead tree | black obsidian rock with glowing cracks | volcanic peak with lava streams |

**Вода** (`<мир>_water.png`, 512×256, бесшовный ромб): озеро. Для пустыни это оазис, для снегов
лёд, для пепла лава.

## Как подключить

1. Положи PNG в нужную папку с именем из таблицы.
2. Напиши мне, какие файлы готовы. Я отмечу их в `pngArt.ts` и проверю, как они выглядят на карте.
