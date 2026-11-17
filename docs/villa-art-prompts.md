# «Моя вилла» — промпты для картинок

Каждый промпт самостоятельный: копируй блок целиком, по одной картинке на запрос.

**Как генерировать**
- Одна картинка — один предмет. Не листы и не наборы.
- Квадрат 1024×1024 (широкие предметы: 1536×1024).
- Если генератор не умеет прозрачный фон, замени в промпте строку `Background: ...`:
  - для всего, кроме воды — `Background: one flat solid pure cyan #00FFFF colour, no gradient, no texture, no vignette.`;
  - для бассейнов — `Background: one flat solid pure magenta #FF00FF colour, no gradient, no texture, no vignette.`

  Плоский цветной фон я уберу чисто, а белый срезается вместе с белыми сетками, заборами и колоннами.
- Масштаб: 1 клетка участка ≈ 2 метра. Размеры клеток в промптах — это размер основания на участке.

Сокращения в промптах:
- «left side» — ребро, идущее от левого угла к переднему (нижнему);
- «right side» — ребро от переднего угла к правому.

---

## Дома и постройки

### villa_1 — Вилла, уровень 1 (4×4)
```
A small cosy Mediterranean cottage villa: one storey, warm cream stucco walls, a terracotta hip roof, green wooden shutters, a small arched porch with two columns and a balustrade, two steps up to a green front door, a few potted geraniums. Real size about 8×8 m, roof ridge about 5 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 4×4 tiles; its walls stand right on the diamond edges, left side 4 tiles, right side 4 tiles, the front corner of the house is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### villa_2 — Вилла, уровень 2 (4×4)
```
A two-storey Mediterranean villa: warm ochre stucco, terracotta tiled roof, green shutters, a ground-floor arcade of three arches, a wrought-iron balcony on the first floor, pink bougainvillea climbing one corner. Real size about 8×8 m, about 8 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 4×4 tiles; its walls stand right on the diamond edges, left side 4 tiles, right side 4 tiles, the front corner of the house is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### villa_3 — Вилла, уровень 3 (4×4)
```
A large two-storey Riviera villa with a small chimney tower: ochre and coral-red stucco wings, terracotta roofs, a roof terrace with a white balustrade and two sun loungers, an arched loggia on the ground floor, green shutters, bougainvillea over the balconies. Real size about 8×8 m, about 9 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 4×4 tiles; its walls stand right on the diamond edges, left side 4 tiles, right side 4 tiles, the front corner of the house is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### villa_4 — Вилла, уровень 4 (4×4)
```
A luxurious three-storey Riviera villa: pale golden limestone, white stone columns, a terracotta roof with a small belvedere tower, a big roof terrace with a glass railing and a tiny plunge pool, tall arched windows, balconies with flowers, a grand front staircase. Real size about 8×8 m, about 11 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 4×4 tiles; its walls stand right on the diamond edges, left side 4 tiles, right side 4 tiles, the front corner of the house is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### villa_5 — Вилла, уровень 5 (4×4)
```
A football superstar's palace villa on the Riviera: white and gold limestone, a central dome, terracotta side roofs, a colonnade, a rooftop infinity pool with turquoise water, a gold football-shaped finial on the dome, palm trees in big stone pots at the entrance, glowing warm windows. Real size about 8×8 m, about 13 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 4×4 tiles; its walls stand right on the diamond edges, left side 4 tiles, right side 4 tiles, the front corner of the house is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### garage_1 — Гараж, уровень 1 (2×2)
```
A small single-car garage: sandstone block walls, a terracotta gable roof, one white roller door on the left wall, a small square window on the right wall, a wall lantern. Real size about 4×4 m, about 3.5 m high — clearly much smaller than a two-storey villa.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 2×2 tiles; its walls stand right on the diamond edges, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### garage_2 — Гараж, уровень 2 (2×2)
```
A neat two-car garage: sandstone block walls, a terracotta roof, two arched cream roller doors side by side on the left wall with a wrought-iron lantern between them, plain stone right wall. Real size about 4×4 m, about 3.5 m high — clearly much smaller than a two-storey villa.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 2×2 tiles; its walls stand right on the diamond edges, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### garage_3 — Гараж, уровень 3 (2×2)
```
A modern luxury showroom garage: sandstone corners, a terracotta hip roof, two dark grey sectional doors on the left wall, a full-height glass wall on the right with a glowing interior and a silver sports car visible inside, slim wall lights. Real size about 4×4 m, about 3.5 m high — clearly much smaller than a two-storey villa.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the building stands on an isometric diamond of 2×2 tiles; its walls stand right on the diamond edges, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### garage_guest — Гостевой гараж (2×2)
```
An open guest carport: four sandstone pillars, a light terracotta roof, a vine-covered wooden pergola beam along one side, a clean stone floor, no walls, no car inside. Real size about 4×4 m, about 3 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its floor fills the diamond exactly, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate around the floor, no cast shadow outside the floor, no text, no frame; the whole object in frame with a small margin.
```

### gazebo_bbq — Беседка с грилем (2×2)
```
A Mediterranean garden gazebo: four white stone columns, a terracotta hip roof, inside a brick barbecue grill with a little smoke, a small wooden table with two chairs, a stone floor. Real size about 4×4 m, about 3.5 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its floor fills the diamond exactly, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate around the floor, no cast shadow outside the floor, no text, no frame; the whole object in frame with a small margin.
```

### pergola_bbq — Летняя кухня (2×2)
```
An outdoor summer kitchen under a wooden pergola: four square wooden posts on sandstone bases, open slatted wooden roof, a cream stone counter with a built-in charcoal grill and a sink, a cutting board, two wooden bar stools, a stone tile floor. Real size about 4×4 m, about 3 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its floor fills the diamond exactly, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate around the floor, no cast shadow outside the floor, no text, no frame; the whole object in frame with a small margin.
```

### trophy_pavilion — Павильон трофеев (2×2)
```
A small round classical trophy pavilion: white marble columns, a golden dome, inside on a pedestal a big golden football cup glowing softly, marble steps around. Real size about 4×4 m, about 4.5 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front at exactly 45°, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its round marble base is inscribed in the diamond, the lowest point of the picture is the front of the base.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### patio_pool — Патио с бассейном (4×4)
```
A luxury patio corner: a sandstone-paved square terrace, a rectangular turquoise pool taking the front half, behind it a small open cabana with a terracotta roof, white cushions inside and pink bougainvillea over it, two wooden sun loungers with striped towels, a cream parasol, a lemon tree and a cypress in big pots. Real size about 8×8 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the terrace fills an isometric diamond of 4×4 tiles exactly, left side 4 tiles, right side 4 tiles, the front corner of the terrace is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass around the terrace, no cast shadow outside it, no text, no frame; the whole object in frame with a small margin.
```

---

## Поля и бассейн

### pitch_mini — Мини-поле с забором (4×4)
```
A small private football pitch: bright striped artificial grass with white markings (centre circle, halfway line, two small penalty boxes), a small white goal with a net at each end, a low sandstone kerb all around and a light white net fence on thin posts along all four sides. Real size about 8×8 m. The goals and the fence must be solid opaque white with clear grey shading, no transparency in the nets.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the pitch fills an isometric diamond of 4×4 tiles exactly, left side 4 tiles, right side 4 tiles, the front corner of the kerb is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass or ground outside the kerb, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### pitch_five — Поле для пятёрок (3×6)
```
A long five-a-side football pitch: striped green artificial grass with white markings (centre circle, halfway line, two penalty areas), a white goal with a net at each short end, a sandstone kerb around it, terracotta pots with pink flowers at the four corners. The long sides run to the right. Real size about 6×12 m. The goals must be solid opaque white with grey shading, no see-through nets.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the pitch fills an isometric rectangle of 3×6 tiles exactly: the left side is 3 tiles (a short end with a goal), the right side is 6 tiles (a long side); the front corner of the kerb is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass or ground outside the kerb, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### pool — Бассейн (3×2)
```
A rectangular garden swimming pool: clear turquoise water with gentle sunlit ripples, blue mosaic tiles inside, a wide cream sandstone coping all around, a chrome ladder at the back. Real size about 6×4 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, no vanishing points.
Footprint: the coping fills an isometric rectangle of 3×2 tiles exactly: left side 3 tiles, right side 2 tiles; the front corner of the coping is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass around, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

---

## Заборы

Каждый вид забора — **4 картинки**:
- **A** — секция на одну клетку, идёт снизу-слева вверх-направо;
- **B** — такая же секция, идёт сверху-слева вниз-направо;
- **post** — отдельный столбик;
- **gate** — калитка на одну клетку в направлении A.

Пример ниже — для каменной ограды. Для остальных видов меняется только первая строка, остальной текст такой же.

### fence_stone_a — Каменная ограда, секция A
```
One straight section of a low Mediterranean garden wall: rough sandstone blocks with a terracotta tile cap, about 1 m high and 2 m long. The section runs diagonally from the lower left up to the upper right (one isometric tile edge long), with a slightly thicker pillar at each end.
Camera: strict 2:1 isometric game projection (true pixel isometry: the bottom edge of the wall rises exactly 1 px for every 2 px sideways, 26.57°), no perspective, all vertical lines perfectly vertical.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). Only the wall section — no ground, no grass, no plate, no cast shadow, no text, no frame; the whole section in frame with a small margin.
```

### fence_stone_b — Каменная ограда, секция B
```
One straight section of a low Mediterranean garden wall: rough sandstone blocks with a terracotta tile cap, about 1 m high and 2 m long. The section runs diagonally from the upper left down to the lower right (one isometric tile edge long), with a slightly thicker pillar at each end.
Camera: strict 2:1 isometric game projection (true pixel isometry: the bottom edge of the wall drops exactly 1 px for every 2 px sideways, 26.57°), no perspective, all vertical lines perfectly vertical.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). Only the wall section — no ground, no grass, no plate, no cast shadow, no text, no frame; the whole section in frame with a small margin.
```

### fence_stone_post — Каменная ограда, столбик
```
A single square sandstone garden-wall pillar with a terracotta tile cap, about 1.2 m high, standing alone.
Camera: strict 2:1 isometric game projection (true pixel isometry, 26.57°), seen from a corner at exactly 45°, no perspective, all vertical lines perfectly vertical.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow, no text, no frame; the whole pillar in frame with a small margin.
```

### fence_stone_gate — Каменная ограда, калитка
```
A garden gate one tile wide in a low sandstone wall: two sandstone pillars with terracotta caps and between them an open wrought-iron gate, about 1.3 m high, 2 m wide. The gate runs diagonally from the lower left up to the upper right (one isometric tile edge long).
Camera: strict 2:1 isometric game projection (true pixel isometry: the bottom line rises exactly 1 px for every 2 px sideways, 26.57°), no perspective, all vertical lines perfectly vertical.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow, no text, no frame; the whole gate in frame with a small margin.
```

Первая строка для остальных видов (вместо описания каменной стены):

- **fence_iron** — Кованая ограда:
  `black wrought-iron railings with golden spear tips on a low sandstone plinth, about 1.2 m high`. Калитка: `an ornate black wrought-iron gate with golden details between two sandstone pillars`.
- **fence_picket** — Белый заборчик:
  `a white painted wooden picket fence with pointed tops, about 1 m high, solid opaque white with soft grey shading`. Калитка: `a white wooden picket gate between two white posts`.
- **fence_hedge** — Изгородь-ограда:
  `a neatly trimmed dense green boxwood hedge, about 1 m high, square cut`. Калитка: `a gap in the boxwood hedge with a small white wooden arch over it`. Столбик: `a round trimmed boxwood ball on a short stem`.

---

## Новые дорожки (1×1, плоские плитки)

Дорожка — плоская плитка, которая бесшовно стыкуется с копиями себя со всех четырёх сторон.

### path_gravel — Гравийная дорожка
```
One flat isometric floor tile: light beige garden gravel with a few small pebbles, completely flat (no kerb, no height). The tile is an exact 2:1 isometric diamond (twice as wide as tall) that fills the whole picture from edge to edge, designed to tile seamlessly with copies of itself on all four edges.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft even light, clean texture, readable at small size.
Background: fully transparent (PNG with alpha channel) outside the diamond. No shadow, no text, no frame.
```

### path_terracotta — Терракотовая плитка
```
One flat isometric floor tile: warm terracotta square clay tiles laid 2×2 with thin cream grout, completely flat. The tile is an exact 2:1 isometric diamond (twice as wide as tall) that fills the whole picture from edge to edge, designed to tile seamlessly with copies of itself on all four edges.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft even light, clean texture, readable at small size.
Background: fully transparent (PNG with alpha channel) outside the diamond. No shadow, no text, no frame.
```

### path_deck — Деревянный настил
```
One flat isometric floor tile: warm honey-coloured wooden deck boards running parallel to one diamond edge, with tiny dark gaps and a few nail heads, completely flat. The tile is an exact 2:1 isometric diamond (twice as wide as tall) that fills the whole picture from edge to edge, designed to tile seamlessly with copies of itself on all four edges.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft even light, clean texture, readable at small size.
Background: fully transparent (PNG with alpha channel) outside the diamond. No shadow, no text, no frame.
```

### path_stepping — Камни в траве
```
One flat isometric floor tile: bright green lawn with three flat round grey-beige stepping stones set into it, completely flat. The tile is an exact 2:1 isometric diamond (twice as wide as tall) that fills the whole picture from edge to edge, designed to tile seamlessly with copies of itself on all four edges.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft even light, clean texture, readable at small size.
Background: fully transparent (PNG with alpha channel) outside the diamond. No shadow, no text, no frame.
```

---

## Новые объекты

Хвост у всех один и тот же, он уже включён в каждый промпт.

### chicken_coop — Курятник (2×2)
```
A charming wooden chicken coop: a small hen house on short legs painted pale blue with a red tin roof, a little ramp, a wire-mesh run fenced with white wooden posts, three white and brown hens and a rooster, a feeder and some straw. Real size about 4×4 m, about 2.5 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its fenced run fills the diamond exactly, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass outside the footprint, no cast shadow outside it, no text, no frame; the whole object in frame with a small margin.
```

### lion_enclosure — Вольер со львом (3×3)
```
A luxury lion enclosure for a football star: a sandstone-walled pen with tall black iron bars and golden finials, inside a patch of savanna grass, a big flat rock, a small pool and a proud male lion with a golden mane lying on the rock, a little shade canopy. Real size about 6×6 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible sides equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the enclosure fills an isometric diamond of 3×3 tiles exactly, left side 3 tiles, right side 3 tiles, the front corner of its wall is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass outside the enclosure, no cast shadow outside it, no text, no frame; the whole object in frame with a small margin.
```

### staff_house — Домик персонала (3×2)
```
A small staff cottage: one storey, whitewashed walls, a terracotta roof, blue shutters, a little covered porch with a bench, a bicycle leaning on the wall, a washing line with white towels, a pot of lavender. Real size about 6×4 m, about 4 m high — clearly smaller than the main villa.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric rectangle of 3×2 tiles: left side 3 tiles, right side 2 tiles; its walls stand right on the edges, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### dog_kennel — Будка с собакой (1×1)
```
A cute wooden dog kennel painted in red and white football-club stripes, with a little terracotta roof, a bone-shaped name sign, a water bowl and a friendly golden retriever lying in front of it with a football between its paws. Real size about 1.5×1.5 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: it stands on one isometric diamond tile, the front corner of its base is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### greenhouse — Оранжерея (2×2)
```
A Victorian-style glass greenhouse: a white painted iron frame, a pitched glass roof, inside lush green plants, tomatoes, lemon saplings and flower pots, the door slightly open. The glass is clear but slightly bluish and fully opaque in the picture (no see-through to the background). Real size about 4×4 m, about 3 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric diamond of 2×2 tiles; its walls stand right on the diamond edges, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass outside, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### vegetable_garden — Огород (2×2)
```
A neat raised vegetable garden: four wooden raised beds with tomatoes on stakes, lettuce, pumpkins and herbs, narrow gravel paths between them, a watering can and a small scarecrow wearing a football scarf. Real size about 4×4 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the garden fills an isometric diamond of 2×2 tiles exactly, left side 2 tiles, right side 2 tiles, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass outside the footprint, no cast shadow outside it, no text, no frame; the whole object in frame with a small margin.
```

### stable — Конюшня (3×2)
```
A small elegant horse stable: sandstone walls, a terracotta roof with a little weather-vane cupola, two half-open wooden stable doors on the left wall with a brown horse and a white horse looking out, a hay bale and a saddle on a rail. Real size about 6×4 m, about 4 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, both visible walls equally foreshortened, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: it stands on an isometric rectangle of 3×2 tiles: left side 3 tiles, right side 2 tiles; its walls stand right on the edges, the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no grass, no plate, no cast shadow on the ground, no text, no frame; the whole object in frame with a small margin.
```

### tennis_court — Теннисный корт (3×5)
```
A private clay tennis court: orange-red clay surface with crisp white lines, a net across the middle on two dark green posts, a low dark green fence along the two long sides, an umpire chair. The long sides run to the right. Real size about 6×10 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, no vanishing points, all vertical lines perfectly vertical.
Footprint: the court fills an isometric rectangle of 3×5 tiles exactly: the left side is 3 tiles (a short end), the right side 5 tiles (a long side); the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass outside the court, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### treehouse — Домик на дереве (2×2)
```
A big old olive tree with a wooden treehouse in its crown: a small plank cabin with a red roof, a rope ladder, a little balcony with a tiny flag of a football club, a tyre swing hanging from a branch. Real size about 4×4 m at the base, about 7 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry, 26.57°), seen from the front at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: the trunk and roots stand in the middle of an isometric diamond of 2×2 tiles; the lowest point of the picture is the front of the roots.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### flamingo_pond — Пруд с фламинго (2×2)
```
A small natural garden pond: clear blue-green water edged with rounded beige stones and reeds, two water lilies, and two pink flamingos standing in the water. Real size about 4×4 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: the pond with its stones is inscribed in an isometric diamond of 2×2 tiles; the lowest point of the picture is the front stone.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass around, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### beehive — Пасека (1×1)
```
Two small wooden beehives painted pale yellow and white on a low stand, a few cartoon bees around them, a pot of lavender beside. Real size about 1.5×1.5 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: it stands on one isometric diamond tile, the front corner of its base is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### hammock — Гамак между пальмами (2×1)
```
A striped canvas hammock in red and white hanging between two small palm trees, a football and a coconut cocktail on the sand-coloured ground beneath it. Real size about 4×2 m.
Camera: strict 2:1 isometric game projection (true pixel isometry: every ground edge rises exactly 1 px for every 2 px sideways, 26.57°), seen from the front corner at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: it stands on an isometric rectangle of 2×1 tiles: the hammock runs along the left side (2 tiles), the right side is 1 tile; the front corner is the lowest point of the picture.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich warm colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No grass, no plate, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```

### basketball_hoop — Баскетбольное кольцо (1×1)
```
A street basketball hoop on a single black pole with a white backboard and an orange rim with a white net, a basketball on the ground next to it. The net is solid opaque white. Real size about 1.5×1.5 m at the base, about 3.5 m high.
Camera: strict 2:1 isometric game projection (true pixel isometry, 26.57°), seen from the front corner at exactly 45°, no perspective, all vertical lines perfectly vertical.
Footprint: the pole stands in the middle of one isometric diamond tile; the lowest point of the picture is the front of its base.
Style: polished casual mobile game art, sunny Côte d'Azur mood, soft afternoon light from the upper left, rich colours, clean shapes, readable at small size.
Background: fully transparent (PNG with alpha channel). No ground, no plate, no cast shadow, no text, no frame; the whole object in frame with a small margin.
```
