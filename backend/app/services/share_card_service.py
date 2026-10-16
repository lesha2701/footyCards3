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
