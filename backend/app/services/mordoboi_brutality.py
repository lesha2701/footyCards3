"""«Бруталити» — joke finishers after a «Мордобой» win.

Each one is a Cosmetic of kind "brutality" (sold in «Стиль» like frames;
price, picture and the coins it adds to the win — `win_bonus_coins` — are
edited in the admin cosmetics list). The `style_key` picks the joke here
and the animation on the frontend (components/mordoboi/BrutalityShow.tsx).
Never touches the result or rating; only the small coin bonus is real.

Phrase placeholders, so the beaten side reads «тебе» instead of «ему»:
{him} ему/тебе · {on_him} него/тебя (after a preposition) · {acc} его/тебя.
"""

KIND = "brutality"

# style_key -> (emoji, what the winner did, past tense)
BRUTALITIES: dict[str, tuple[str, str]] = {
    "flick": ("👉", "отвесил {him} звонкий щелбан"),
    "fart": ("💨", "пернул {him} прямо под нос"),
    "underpants": ("🩲", "надел {him} труханы на голову"),
    "wet_willy": ("👂", "засунул {him} мокрый палец в ухо"),
    "sock": ("🧦", "засунул {him} в рот грязный носок"),
    "armpit": ("🤢", "ткнул {acc} носом в потную подмышку"),
    "cake": ("🎂", "впечатал {him} торт в лицо"),
    "diaper": ("🍼", "надел на {on_him} памперс и дал соску"),
    "chicken": ("🐔", "заставил {acc} кудахтать курицей на весь стадион"),
    "clown": ("🤡", "нарисовал {him} красный клоунский нос"),
    "tickle": ("🪶", "защекотал {acc} пёрышком до икоты"),
    "bucket": ("🪣", "вылил на {on_him} ведро ледяной воды"),
    "lipstick": ("💋", "накрасил {him} губы помадой и сфоткал"),
    "baby_song": ("🎶", "спел {him} колыбельную, пока он лежал"),
}

# Seeded by migration 0193: (style_key, name, description, coins, stars, sort).
# Stars from 100 ⭐, one entry-level finisher for coins; each adds 10 coins
# to the win (admin-editable per item).
SEED = (
    ("flick", "Щелбан", "Звонкий щелбан поверженному сопернику", 1000, 0, 1),
    ("fart", "Газовая атака", "Пёрнуть сопернику прямо под нос", 0, 100, 2),
    ("underpants", "Труханы на голову", "Надеть сопернику трусы на голову", 0, 100, 3),
    ("clown", "Клоунский нос", "Красный нос — теперь он клоун", 0, 100, 4),
    ("tickle", "Щекотка", "Защекотать пёрышком до икоты", 0, 100, 5),
    ("wet_willy", "Мокрый палец", "Мокрый палец в ухо — классика жанра", 0, 120, 6),
    ("lipstick", "Помада", "Накрасить губы и сделать фото на память", 0, 120, 7),
    ("sock", "Носок в рот", "Грязный носок прямо в рот", 0, 150, 8),
    ("armpit", "Подмышка", "Ткнуть носом в потную подмышку", 0, 150, 9),
    ("bucket", "Ведро воды", "Ледяной душ для проигравшего", 0, 150, 10),
    ("baby_song", "Колыбельная", "Спеть колыбельную нокаутированному", 0, 150, 11),
    ("cake", "Торт в лицо", "Кремовый торт в лицо проигравшему", 0, 200, 12),
    ("diaper", "Памперс", "Памперс и соска для проигравшего", 0, 200, 13),
    ("chicken", "Курица", "Проигравший кудахчет на весь стадион", 0, 250, 14),
)
SEED_WIN_BONUS = 10


def emoji(style_key: str) -> str:
    return BRUTALITIES.get(style_key, ("🥊", ""))[0]


def phrase(style_key: str, name: str, to_viewer: bool) -> str:
    """«надел ему труханы на голову» (or «тебе» for the beaten side)."""
    template = BRUTALITIES.get(style_key, ("", ""))[1]
    if not template:
        return f"сделал {'тебе' if to_viewer else 'ему'} «{name}»"
    if to_viewer:
        return template.format(him="тебе", on_him="тебя", acc="тебя").replace("пока он лежал", "пока ты лежал")
    return template.format(him="ему", on_him="него", acc="его")
