"""Renders the share images players send to Telegram chats (a lucky card,
an Arena win, a trophy). Drawn on the server from the player's own data
only — a client-generated image could be anything, and the prepared
message carries the bot's name.

Pure rendering: callers pass plain values, this module returns JPEG bytes.
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_HEAVY = FONT_DIR / "benzin-extrabold.woff2"
FONT_BOLD = FONT_DIR / "benzin-bold.woff2"

SIZE = 800
BG_TOP = (9, 16, 12)
BG_BOTTOM = (20, 52, 33)
WHITE = (243, 246, 242)
MIST = (160, 172, 164)
LIME = (198, 230, 58)
GREEN = (62, 209, 126)

RARITY_COLORS = {
    "common": (148, 163, 184),
    "rare": (59, 130, 246),
    "epic": (168, 85, 247),
    "legendary": (245, 158, 11),
    "diamond": (103, 232, 249),
}
RARITY_LABELS = {
    "common": "Обычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
    "diamond": "Бриллиантовая",
}


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _fit(draw: ImageDraw.ImageDraw, text: str, path: Path, start: int, max_width: int, min_size: int = 18):
    """Largest font size (from `start` down) at which `text` fits `max_width`."""
    size = start
    while size > min_size:
        font = _font(path, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 2
    return _font(path, min_size)


def _center(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill) -> None:
    w = draw.textlength(text, font=font)
    draw.text(((SIZE - w) / 2, y), text, font=font, fill=fill)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 2) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def _base(headline: str, bot_username: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE, SIZE), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(SIZE):  # vertical gradient, "stadium at night"
        t = y / SIZE
        draw.line([(0, y), (SIZE, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    brand = _font(FONT_HEAVY, 34)
    w1 = draw.textlength("VICTOR ", font=brand)
    w2 = draw.textlength("FC", font=brand)
    x = (SIZE - w1 - w2) / 2
    draw.text((x, 36), "VICTOR ", font=brand, fill=WHITE)
    draw.text((x + w1, 36), "FC", font=brand, fill=LIME)
    _center(draw, 92, headline, _fit(draw, headline, FONT_HEAVY, 46, SIZE - 80), GREEN)

    _center(draw, SIZE - 92, "Собирай карточки футболистов в Telegram", _font(FONT_BOLD, 22), MIST)
    _center(draw, SIZE - 58, f"@{bot_username}", _font(FONT_HEAVY, 26), LIME)
    return img, draw


def _paste_rounded(img: Image.Image, art: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    x0, y0, x1, y1 = box
    art = ImageOps.fit(art.convert("RGB"), (x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, art.size[0] - 1, art.size[1] - 1], radius=radius, fill=255)
    img.paste(art, (x0, y0), mask)


def _load(path: Optional[Path]) -> Optional[Image.Image]:
    if path is None or not path.is_file():
        return None
    try:
        with Image.open(path) as im:
            im.load()
            return im.copy()
    except OSError:
        return None


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue()


def render_card(*, name: str, rating: int, position: str, rarity: str, image: Optional[Path], bot_username: str) -> bytes:
    headline = "Бриллиант в коллекции!" if rarity == "diamond" else "Выпала легенда!" if rarity == "legendary" else "Новая карточка!"
    img, draw = _base(headline, bot_username)
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])

    box = (SIZE // 2 - 165, 170, SIZE // 2 + 165, 560)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, alpha in enumerate((60, 40, 22)):
        pad = 8 + i * 8
        gd.rounded_rectangle([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad], radius=34 + pad, outline=color + (alpha,), width=8)
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(box, radius=30, fill=(16, 24, 18), outline=color, width=6)

    art = _load(image)
    inner = (box[0] + 6, box[1] + 6, box[2] - 6, box[3] - 6)
    if art is not None:
        _paste_rounded(img, art, inner, 24)
        draw = ImageDraw.Draw(img)
    else:
        initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
        _center(draw, (box[1] + box[3]) // 2 - 50, initials, _font(FONT_HEAVY, 90), color)

    # Rating badge in the card's top-left corner
    draw.rounded_rectangle([box[0] + 14, box[1] + 14, box[0] + 104, box[1] + 104], radius=18, fill=(8, 12, 10))
    rating_font = _font(FONT_HEAVY, 44)
    rw = draw.textlength(str(rating), font=rating_font)
    draw.text((box[0] + 59 - rw / 2, box[1] + 22), str(rating), font=rating_font, fill=color)
    pos_font = _font(FONT_BOLD, 18)
    pw = draw.textlength(position, font=pos_font)
    draw.text((box[0] + 59 - pw / 2, box[1] + 74), position, font=pos_font, fill=WHITE)

    _center(draw, 584, name, _fit(draw, name, FONT_HEAVY, 44, SIZE - 80), WHITE)
    _center(draw, 640, f"{RARITY_LABELS.get(rarity, rarity)} карточка", _font(FONT_BOLD, 26), color)
    return _jpeg(img)


def render_match_win(*, user_score: int, opponent_score: int, player_name: str, bot_username: str) -> bytes:
    img, draw = _base("Победа в Card Arena!", bot_username)
    score = f"{user_score} : {opponent_score}"
    _center(draw, 250, score, _fit(draw, score, FONT_HEAVY, 190, SIZE - 120), WHITE)
    _center(draw, 500, player_name, _fit(draw, player_name, FONT_HEAVY, 40, SIZE - 120), LIME)
    _center(draw, 560, "выигрывает матч своим составом", _font(FONT_BOLD, 26), MIST)
    return _jpeg(img)


def render_trophy(*, name: str, description: str, image: Optional[Path], bot_username: str) -> bytes:
    img, draw = _base("Новый трофей!", bot_username)
    art = _load(image)
    if art is not None:
        art = ImageOps.contain(art.convert("RGBA"), (300, 300), Image.Resampling.LANCZOS)
        img.paste(art, ((SIZE - art.width) // 2, 175 + (300 - art.height) // 2), art)
        draw = ImageDraw.Draw(img)
    else:
        # Simple cup when the trophy has no image (its emoji icon can't be drawn with the brand font).
        cx, top = SIZE // 2, 200
        draw.pieslice([cx - 110, top - 40, cx + 110, top + 200], 0, 180, fill=LIME)
        draw.rectangle([cx - 110, top - 40, cx + 110, top + 80], fill=LIME)
        draw.rectangle([cx - 16, top + 190, cx + 16, top + 250], fill=LIME)
        draw.rounded_rectangle([cx - 80, top + 250, cx + 80, top + 285], radius=8, fill=LIME)
    _center(draw, 505, name, _fit(draw, name, FONT_HEAVY, 46, SIZE - 80), WHITE)
    body = _font(FONT_BOLD, 24)
    for i, line in enumerate(_wrap(draw, description, body, SIZE - 140)):
        _center(draw, 566 + i * 34, line, body, MIST)
    return _jpeg(img)


# «Мой игрок»: the constructor's option palettes (frontend lib/myPlayer.ts).
_SKIN = ["#f6d7c3", "#eac0a0", "#d7a27c", "#b67b52", "#8d5a3b", "#5e3b26"]
_HAIR = ["#1f1a17", "#4a2f1f", "#7b4a26", "#c08a3e", "#e3c27a", "#a33a1f", "#bdbdbd"]
_EYES = ["#4a3426", "#24160d", "#3b82c4", "#3f8f5a", "#7b8794", "#8a6a2f"]
_KITS = ["#d62828", "#1d4ed8", "#38bdf8", "#15803d", "#facc15", "#f97316", "#7c3aed", "#18181b", "#f4f4f5", "#7f1d1d"]
TIER_COLORS = {"bronze": (205, 127, 50), "silver": (203, 213, 225), "gold": (250, 204, 21), "legend": (232, 121, 249)}
_BALD, _LONG, _MOHAWK, _AFRO = 7, 4, 5, 6


def _rgb(hex_color: str) -> tuple[int, int, int]:
    n = int(hex_color.lstrip("#"), 16)
    return n >> 16, (n >> 8) & 255, n & 255


def _pick(palette: list[str], index: int) -> tuple[int, int, int]:
    return _rgb(palette[index] if 0 <= index < len(palette) else palette[0])


def _draw_avatar(img: Image.Image, box: tuple[int, int, int, int], appearance: dict, number: int) -> None:
    """A flat version of the constructor's avatar (components/myPlayer/PlayerAvatar.tsx)."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = layer.size
    cx = w // 2
    skin, hair = _pick(_SKIN, appearance.get("skin", 0)), _pick(_HAIR, appearance.get("hair_color", 0))
    kit, eyes = _pick(_KITS, appearance.get("kit", 0)), _pick(_EYES, appearance.get("eye_color", 0))
    style, beard = appearance.get("hair", 0), appearance.get("beard", 0)
    light_kit = appearance.get("kit", 0) in (4, 8)
    head = (cx - 72, 70, cx + 72, 250)

    if style == _AFRO:
        d.ellipse((cx - 112, 34, cx + 112, 240), fill=hair)
    if style == _LONG:
        d.rounded_rectangle((cx - 86, 120, cx + 86, 300), radius=40, fill=hair)
    # torso and kit
    d.rounded_rectangle((cx - 150, 275, cx + 150, h + 60), radius=90, fill=kit)
    if appearance.get("kit_pattern") == 1:
        for sx in range(cx - 130, cx + 140, 52):
            d.rectangle((sx, 290, sx + 18, h), fill=(255, 255, 255) if not light_kit else (29, 78, 216))
    elif appearance.get("kit_pattern") == 2:
        for sy in (320, 356):
            d.rectangle((cx - 150, sy, cx + 150, sy + 16), fill=(255, 255, 255) if not light_kit else (29, 78, 216))
    d.rectangle((cx - 34, 220, cx + 34, 292), fill=skin)
    d.pieslice((cx - 40, 258, cx + 40, 316), 0, 180, fill=skin)
    num_font = _font(FONT_HEAVY, 46)
    label = str(number)
    d.text((cx + 52 - d.textlength(label, font=num_font) / 2, 318), label, font=num_font,
           fill=(24, 24, 27) if light_kit else (255, 255, 255))
    # ears + head
    for ex in (cx - 76, cx + 76):
        d.ellipse((ex - 14, 150, ex + 14, 190), fill=skin)
    d.ellipse(head, fill=skin)
    # hair on top
    if style == _MOHAWK:
        d.rounded_rectangle((cx - 16, 40, cx + 16, 120), radius=14, fill=hair)
    elif style not in (_BALD,):
        d.chord((cx - 76, 60, cx + 76, 190), 180, 360, fill=hair)
        d.rectangle((cx - 74, 116, cx - 62, 160), fill=hair)
        d.rectangle((cx + 62, 116, cx + 74, 160), fill=hair)
    # beard
    if beard == 1:
        stubble = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(stubble).chord((cx - 70, 120, cx + 70, 250), 15, 165, fill=hair + (80,))
        layer.alpha_composite(stubble)
        d = ImageDraw.Draw(layer)
    elif beard in (2, 3):
        d.chord((cx - 70 if beard == 3 else cx - 26, 150, cx + 70 if beard == 3 else cx + 26, 252), 20, 160, fill=hair)
    if beard in (2, 3, 4):
        d.rounded_rectangle((cx - 28, 196, cx + 28, 206), radius=5, fill=hair)
    # brows, eyes, mouth
    for side in (-1, 1):
        ex = cx + side * 32
        d.line((ex - 16, 142, ex + 14, 138), fill=tuple(max(0, c - 40) for c in hair), width=6)
        d.ellipse((ex - 15, 154, ex + 15, 174), fill=(255, 255, 255))
        d.ellipse((ex - 8, 156, ex + 8, 172), fill=eyes)
        d.ellipse((ex - 4, 160, ex + 4, 168), fill=(13, 13, 13))
    if beard != 3:
        d.arc((cx - 22, 196, cx + 22, 226), 20, 160, fill=(122, 52, 40), width=5)
    img.paste(layer, (x0, y0), layer)


def render_my_player(
    *, name: str, number: int, position: str, rating: int, attack: int, defense: int, level: int,
    tier: str, tier_label: str, appearance: dict, bot_username: str,
) -> bytes:
    img, draw = _base("Мой игрок в Victor FC!", bot_username)
    color = TIER_COLORS.get(tier, TIER_COLORS["bronze"])
    box = (SIZE // 2 - 170, 165, SIZE // 2 + 170, 575)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, alpha in enumerate((70, 44, 24)):
        pad = 8 + i * 8
        gd.rounded_rectangle([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad], radius=34 + pad, outline=color + (alpha,), width=8)
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(box, radius=30, fill=(22, 32, 44), outline=color, width=7)
    _draw_avatar(img, (box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8), appearance, number)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([box[0] + 16, box[1] + 16, box[0] + 106, box[1] + 106], radius=18, fill=(8, 12, 10))
    rating_font = _font(FONT_HEAVY, 44)
    rw = draw.textlength(str(rating), font=rating_font)
    draw.text((box[0] + 61 - rw / 2, box[1] + 24), str(rating), font=rating_font, fill=color)
    pos_font = _font(FONT_BOLD, 18)
    pw = draw.textlength(position, font=pos_font)
    draw.text((box[0] + 61 - pw / 2, box[1] + 76), position, font=pos_font, fill=WHITE)
    tier_font = _font(FONT_BOLD, 20)
    label = tier_label.upper()
    draw.rounded_rectangle([box[2] - 26 - draw.textlength(label, font=tier_font), box[1] + 18, box[2] - 14, box[1] + 50], radius=12, fill=(8, 12, 10))
    draw.text((box[2] - 20 - draw.textlength(label, font=tier_font), box[1] + 22), label, font=tier_font, fill=color)

    title = f"{name} #{number}"
    _center(draw, 592, title, _fit(draw, title, FONT_HEAVY, 40, SIZE - 80), WHITE)
    _center(draw, 646, f"АТК {attack} · ЗЩТ {defense} · уровень {level}", _font(FONT_BOLD, 26), color)
    return _jpeg(img)


# --- «Менеджер» ---------------------------------------------------------------------------

# Share-card frames of the club style shop (manager_shop): border + accent.
MANAGER_FRAMES = {
    "classic": ((198, 230, 58), (62, 209, 126)),
    "retro": ((245, 158, 11), (234, 88, 12)),
    "neon": ((34, 211, 238), (232, 121, 249)),
    "gold": ((250, 204, 21), (253, 230, 138)),
    "ruby": ((225, 29, 72), (251, 113, 133)),
    "ice": ((125, 211, 252), (224, 242, 254)),
    "fire": ((249, 115, 22), (250, 204, 21)),
    "galaxy": ((139, 92, 246), (236, 72, 153)),
}
RED = (248, 113, 113)


def _triangle(draw: ImageDraw.ImageDraw, x: float, y: float, size: int, up: bool, fill) -> None:
    if up:
        draw.polygon([(x, y + size), (x + size, y + size), (x + size / 2, y)], fill=fill)
    else:
        draw.polygon([(x, y), (x + size, y), (x + size / 2, y + size)], fill=fill)


def _arrow(draw: ImageDraw.ImageDraw, x: float, y: float, length: int, fill) -> None:
    draw.line([(x, y), (x + length - 14, y)], fill=fill, width=6)
    draw.polygon([(x + length - 18, y - 12), (x + length, y), (x + length - 18, y + 12)], fill=fill)


def _manager_avatar_box(img: Image.Image, frame: str, appearance: dict, number: int, top: int, height: int) -> tuple:
    border, _accent = MANAGER_FRAMES.get(frame, MANAGER_FRAMES["classic"])
    box = (SIZE // 2 - height * 4 // 10, top, SIZE // 2 + height * 4 // 10, top + height)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, alpha in enumerate((70, 44, 24)):
        pad = 8 + i * 8
        gd.rounded_rectangle([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad], radius=34 + pad, outline=border + (alpha,), width=8)
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(box, radius=30, fill=(22, 32, 44), outline=border, width=7)
    # _draw_avatar is laid out for the 340×410 box of render_my_player: draw
    # it at that size and scale it into this (smaller) frame.
    full = Image.new("RGB", (340, 410), (22, 32, 44))
    _draw_avatar(full, (8, 8, 332, 402), appearance, number)
    _paste_rounded(img, full, (box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8), 24)
    return box


def _rating_badge(draw: ImageDraw.ImageDraw, box: tuple, rating: int, position: str, color) -> None:
    draw.rounded_rectangle([box[0] + 14, box[1] + 14, box[0] + 100, box[1] + 100], radius=18, fill=(8, 12, 10))
    rating_font = _font(FONT_HEAVY, 40)
    rw = draw.textlength(str(rating), font=rating_font)
    draw.text((box[0] + 57 - rw / 2, box[1] + 22), str(rating), font=rating_font, fill=color)
    pos_font = _font(FONT_BOLD, 18)
    pw = draw.textlength(position, font=pos_font)
    draw.text((box[0] + 57 - pw / 2, box[1] + 70), position, font=pos_font, fill=WHITE)


def render_manager_player(
    *, name: str, number: int, position: str, rating: int, value_text: str, trend_pct: Optional[int], club_line: str,
    stats_line: str, appearance: dict, frame: str, bot_username: str,
) -> bytes:
    """«Мой игрок» with his transfer value in millions and the weekly trend."""
    img, draw = _base("Моя трансферная стоимость", bot_username)
    border, accent = MANAGER_FRAMES.get(frame, MANAGER_FRAMES["classic"])
    box = _manager_avatar_box(img, frame, appearance, number, 140, 280)
    draw = ImageDraw.Draw(img)
    _rating_badge(draw, box, rating, position, border)
    title = f"{name} #{number}"
    _center(draw, 436, title, _fit(draw, title, FONT_HEAVY, 34, SIZE - 80), WHITE)
    value_font = _fit(draw, value_text, FONT_HEAVY, 72, SIZE - 120, 40)
    _center(draw, 480, value_text, value_font, border)
    if trend_pct:  # None (no history yet) or 0 — nothing to show
        up = trend_pct >= 0
        text = f"{'+' if up else ''}{trend_pct}% за неделю"
        font = _font(FONT_BOLD, 26)
        w = draw.textlength(text, font=font) + 34
        x = (SIZE - w) / 2
        _triangle(draw, x, 576, 22, up, GREEN if up else RED)
        draw.text((x + 34, 570), text, font=font, fill=GREEN if up else RED)
    _center(draw, 614, club_line, _fit(draw, club_line, FONT_BOLD, 26, SIZE - 80), WHITE)
    _center(draw, 652, stats_line, _fit(draw, stats_line, FONT_BOLD, 22, SIZE - 80), accent)
    return _jpeg(img)


def render_transfer(
    *, player_name: str, number: int, position: str, rating: int, from_club: str, to_club: str, fee_text: str,
    kind_label: str, appearance: dict, frame: str, bot_username: str,
) -> bytes:
    """«Here we go!» — a transfer of the transfer market of «Менеджер»."""
    img, draw = _base("HERE WE GO!", bot_username)
    border, accent = MANAGER_FRAMES.get(frame, MANAGER_FRAMES["classic"])
    box = _manager_avatar_box(img, frame, appearance, number, 140, 280)
    draw = ImageDraw.Draw(img)
    _rating_badge(draw, box, rating, position, border)
    _center(draw, 436, player_name, _fit(draw, player_name, FONT_HEAVY, 40, SIZE - 80), WHITE)
    font = _font(FONT_BOLD, 28)
    left = from_club or "Свободный агент"
    lw = min(draw.textlength(left, font=font), 300)
    rw = min(draw.textlength(to_club, font=font), 300)
    total = lw + 80 + rw
    x = (SIZE - total) / 2
    draw.text((x, 490), left, font=_fit(draw, left, FONT_BOLD, 28, 300), fill=MIST)
    _arrow(draw, x + lw + 12, 508, 56, accent)
    draw.text((x + lw + 80, 490), to_club, font=_fit(draw, to_club, FONT_BOLD, 28, 300), fill=WHITE)
    _center(draw, 540, fee_text, _fit(draw, fee_text, FONT_HEAVY, 66, SIZE - 120, 36), border)
    _center(draw, 630, kind_label, _font(FONT_BOLD, 24), accent)
    return _jpeg(img)


# --- «Мордобой»: a knockout GIF -------------------------------------------------------

GIF_SIZE = 480
RED = (229, 57, 53)
YELLOW = (250, 204, 21)


def _gif_card(name: str, rating: int, rarity: str, image: Optional[Path]) -> Image.Image:
    """A small portrait card (RGBA) — the boxer in the ring."""
    w, h = 150, 200
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=16, fill=color)
    draw.rounded_rectangle([5, 5, w - 6, h - 6], radius=12, fill=(14, 22, 18))
    art = _load(image)
    if art is not None:
        _paste_rounded(card, art, (5, 5, w - 5, h - 52), 12)
    else:
        initials = "".join(part[:1] for part in name.split()[:2]).upper() or "?"
        f = _font(FONT_HEAVY, 54)
        tw = draw.textlength(initials, font=f)
        draw.text(((w - tw) / 2, 50), initials, font=f, fill=MIST)
    draw.rounded_rectangle([8, 8, 52, 38], radius=8, fill=(0, 0, 0))
    draw.text((14, 10), str(rating), font=_font(FONT_HEAVY, 22), fill=WHITE)
    nf = _fit(draw, name, FONT_BOLD, 18, w - 16, min_size=11)
    nw = draw.textlength(name, font=nf)
    draw.text(((w - nw) / 2, h - 40), name, font=nf, fill=WHITE)
    return card


def _glove(size: int = 64) -> Image.Image:
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    d.ellipse([4, 4, size - 10, size - 14], fill=RED, outline=(120, 20, 20), width=3)
    d.ellipse([size - 26, size // 2 - 6, size - 4, size // 2 + 14], fill=RED, outline=(120, 20, 20), width=3)  # thumb
    d.rectangle([10, size - 18, size - 22, size - 4], fill=WHITE, outline=(120, 20, 20), width=2)  # cuff
    return g


def _burst(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    import math

    points = []
    for i in range(16):
        rad = r if i % 2 == 0 else r * 0.45
        a = math.pi * 2 * i / 16
        points.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    draw.polygon(points, fill=YELLOW, outline=(200, 120, 0))


def render_knockout_gif(
    *, winner_name: str, winner_rating: int, winner_rarity: str, winner_image: Optional[Path],
    loser_name: str, loser_rating: int, loser_rarity: str, loser_image: Optional[Path],
    headline: str, bot_username: str,
) -> tuple[bytes, bytes]:
    """(GIF bytes, JPEG thumbnail of the last frame): the winner's glove
    flies across the ring, the other card falls, «НОКАУТ!»."""
    left = _gif_card(winner_name, winner_rating, winner_rarity, winner_image)
    right = _gif_card(loser_name, loser_rating, loser_rarity, loser_image)
    glove = _glove()

    def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGB", (GIF_SIZE, GIF_SIZE), BG_TOP)
        draw = ImageDraw.Draw(img)
        for y in range(GIF_SIZE):
            t = y / GIF_SIZE
            draw.line([(0, y), (GIF_SIZE, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
        for i, color in enumerate(((200, 40, 40), (230, 230, 230), (40, 90, 200))):  # ring ropes
            draw.line([(0, 120 + i * 14), (GIF_SIZE, 120 + i * 14)], fill=color, width=3)
        brand = _font(FONT_HEAVY, 24)
        w1, w2 = draw.textlength("МОРДОБОЙ · VICTOR ", font=brand), draw.textlength("FC", font=brand)
        x = (GIF_SIZE - w1 - w2) / 2
        draw.text((x, 18), "МОРДОБОЙ · VICTOR ", font=brand, fill=WHITE)
        draw.text((x + w1, 18), "FC", font=brand, fill=LIME)
        foot = _font(FONT_BOLD, 16)
        tag = f"@{bot_username}"
        draw.text(((GIF_SIZE - draw.textlength(tag, font=foot)) / 2, GIF_SIZE - 30), tag, font=foot, fill=LIME)
        return img, draw

    frames: list[Image.Image] = []
    durations: list[int] = []
    lx, ly, rx, ry = 40, 170, 290, 170

    def frame(glove_x: Optional[int] = None, angle: float = 0, drop: int = 0, burst: bool = False,
              title: Optional[str] = None, ms: int = 110) -> None:
        img, draw = base()
        img.paste(left, (lx, ly), left)
        rot = right.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC) if angle else right
        img.paste(rot, (rx + (right.width - rot.width) // 2, ry + drop + (right.height - rot.height) // 2), rot)
        if glove_x is not None:
            img.paste(glove, (glove_x, ly + 60), glove)
        if burst:
            _burst(draw, rx + 20, ly + 80, 46)
            f = _font(FONT_HEAVY, 26)
            draw.text((rx - 8, ly + 66), "БАМ!", font=f, fill=(120, 20, 20))
        if title:
            f = _font(FONT_HEAVY, 64)
            tw = draw.textlength(title, font=f)
            draw.text(((GIF_SIZE - tw) / 2 + 3, 384 + 3), title, font=f, fill=(0, 0, 0))
            draw.text(((GIF_SIZE - tw) / 2, 384), title, font=f, fill=RED)
            sub = _font(FONT_BOLD, 16)
            for i, line in enumerate(_wrap(draw, headline, sub, GIF_SIZE - 40, max_lines=2)):
                draw.text(((GIF_SIZE - draw.textlength(line, font=sub)) / 2, 62 + i * 22), line, font=sub, fill=WHITE)
        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
        durations.append(ms)

    frame(ms=400)
    for x in range(lx + 120, rx - 30, 40):
        frame(glove_x=x, ms=70)
    frame(glove_x=rx - 30, burst=True, ms=220)
    for step, angle in enumerate((-12, -30, -55, -80, -90), start=1):
        frame(angle=angle, drop=step * 12, ms=90)
    frame(angle=-90, drop=60, title="НОКАУТ!", ms=1800)

    out = io.BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
    thumb = io.BytesIO()
    frames[-1].convert("RGB").save(thumb, format="JPEG", quality=85)
    return out.getvalue(), thumb.getvalue()
