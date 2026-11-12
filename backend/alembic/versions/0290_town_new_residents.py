"""«Жители»: 49 new residents with their professions — police, firefighters
and rescuers, harbour people, pitch keepers, craftsmen, artists and more
(pictures in static/residents/town). Bonuses only on the legendary ones; the
new sets «Службы спасения», «Люди гавани», «Хранители поля», «Мастера
Сан-Виктора» and «Вечер в Сан-Викторе». Inserted only where the picture is
not in the catalog yet, after the admin's own residents.

Revision ID: 0290
Revises: 0289
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0290"
down_revision: Union[str, None] = "0289"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug, name, title, description, icon, rarity, bonus, bonus value, set
RESIDENTS = (
    ('artur', 'Артур', 'управляющий банком', 'Открывает хранилище с памятной футбольной монетой', '🏦', 'legendary', 'rent_pct', 4, None),
    ('valentina', 'Валентина', 'кредитный специалист', 'Изучает проект новой районной футбольной площадки', '📑', 'rare', 'none', 0, None),
    ('alina', 'Алина', 'полицейская', 'Регулирует движение у стадиона в день матча', '👮\u200d♀️', 'epic', 'none', 0, 'Службы спасения'),
    ('migel-patrul', 'Мигел', 'полицейский', 'Выходит на связь по рации во время вечернего патруля', '📻', 'rare', 'none', 0, 'Службы спасения'),
    ('denis', 'Денис', 'кинолог', 'Тренирует овчарку в подтрибунном коридоре', '🐕\u200d🦺', 'rare', 'none', 0, None),
    ('brunu-pozharnyi', 'Бруну', 'пожарный', 'Разворачивает рукав у машины на набережной', '🚒', 'rare', 'none', 0, 'Службы спасения'),
    ('inesh-pozharnaya', 'Инеш', 'пожарная', 'Несёт складную лестницу в депо', '🧯', 'rare', 'none', 0, 'Службы спасения'),
    ('rafael-feldsher', 'Рафаэл', 'фельдшер скорой', 'Готовит медицинскую сумку у кромки поля', '🚑', 'rare', 'none', 0, 'Службы спасения'),
    ('samira', 'Самира', 'диспетчер экстренных служб', 'Принимает вызов во время грозы', '☎️', 'rare', 'none', 0, 'Службы спасения'),
    ('mara', 'Мара', 'спасательница береговой службы', 'Ведёт катер мимо маяка в ветреную погоду', '🚤', 'epic', 'none', 0, 'Службы спасения'),
    ('viktoriya', 'Виктория', 'инженер разводного моста', 'Осматривает механизм моста на рассвете', '🌉', 'epic', 'none', 0, None),
    ('daiti-mori', 'Дайти Мори', 'инженер из Японии', 'Осматривает оборудование трамвайного депо — стройка идёт быстрее', '🚊', 'legendary', 'build_pct', 5, None),
    ('eliash', 'Элиаш', 'ночной диспетчер порта', 'Встречает первый паром по рации', '⚓', 'rare', 'none', 0, 'Люди гавани'),
    ('leon', 'Леон', 'портовый водолаз', 'Осматривает опору пирса и находит затонувший мяч', '🤿', 'epic', 'none', 0, 'Люди гавани'),
    ('renatu', 'Ренату', 'водолаз', 'Поднимает со дна старый клубный вымпел', '🚩', 'rare', 'none', 0, 'Люди гавани'),
    ('lusia-lodki', 'Лусия', 'мастер по ремонту лодок', 'Чинит бирюзовую лодку в гавани', '🛶', 'common', 'none', 0, 'Люди гавани'),
    ('daria', 'Дарья', 'инструктор по парусу из Владивостока', 'Управляет парусом на рассвете', '⛵', 'rare', 'none', 0, 'Люди гавани'),
    ('ingrid', 'Ингрид', 'метеоролог из Бергена', 'Запускает метеозонд с волнореза и знает погоду на каждый матч', '🎈', 'legendary', 'daily_coins', 10, None),
    ('sigrid', 'Сигрид', 'веломеханик из Тронхейма', 'Ставит колесо в мастерской над гаванью', '🔧', 'rare', 'none', 0, None),
    ('zara', 'Зара', 'велокурьер', 'Развозит заказы по крутым улицам Сан-Виктора', '🚲', 'common', 'none', 0, None),
    ('ivo', 'Иво', 'смотритель поля', 'Наносит разметку перед дерби', '🖌️', 'common', 'none', 0, 'Хранители поля'),
    ('teo', 'Тео', 'специалист по газонам', 'Проверяет корни травы на тренировочном поле', '🌱', 'rare', 'none', 0, 'Хранители поля'),
    ('alisa', 'Алиса', 'светодизайнер из Москвы', 'Настраивает прожекторы на макете стадиона', '💡', 'epic', 'none', 0, 'Хранители поля'),
    ('polina', 'Полина', 'реставратор из Петербурга', 'Восстанавливает старую матчевую программку', '📜', 'rare', 'none', 0, 'Мастера Сан-Виктора'),
    ('nina-santos', 'Нина Сантос', 'спортивный фотограф', 'Снимает матч с самой выгодной точки', '📷', 'epic', 'none', 0, None),
    ('yasmin', 'Ясмин', 'ветеринар', 'Осматривает рыжего кота, который живёт на стадионе', '🐈', 'common', 'none', 0, None),
    ('mei', 'Мей', 'мастер неоновых вывесок', 'Включает розовый неоновый мяч над улицей', '🩷', 'rare', 'none', 0, 'Мастера Сан-Виктора'),
    ('naomi', 'Наоми', 'мастер витражей', 'Проверяет цвет стекла на солнце', '🪟', 'rare', 'none', 0, 'Мастера Сан-Виктора'),
    ('leila', 'Лейла', 'часовщица', 'Ремонтирует старый футбольный секундомер', '⏱️', 'epic', 'none', 0, 'Мастера Сан-Виктора'),
    ('aigul', 'Айгуль', 'дизайнер по текстилю из Казани', 'Ткёт шарф болельщиков', '🧣', 'rare', 'none', 0, 'Мастера Сан-Виктора'),
    ('roza-mendes', 'Роза Мендес', 'швея', 'Шьёт флаг для трибун', '🧵', 'common', 'none', 0, 'Мастера Сан-Виктора'),
    ('nadiya', 'Надия', 'экскурсовод', 'Показывает старую карту города под каменной аркой', '🗺️', 'common', 'none', 0, None),
    ('salvador', 'Салвадор', 'мастер воздушных змеев', 'Запускает бирюзового ската над пляжем', '🪁', 'common', 'none', 0, None),
    ('mateush', 'Матеуш', 'мороженщик', 'Подаёт фисташковое мороженое из велотележки', '🍦', 'common', 'none', 0, None),
    ('emma', 'Эмма', 'киномеханик', 'Готовит показ архивного финала на крыше', '🎞️', 'common', 'none', 0, 'Вечер в Сан-Викторе'),
    ('seleste', 'Селеста', 'диджей', 'Ставит винил на празднике победы — в отеле не протолкнуться', '🎧', 'legendary', 'hotel_pct', 5, 'Вечер в Сан-Викторе'),
    ('livia', 'Ливия', 'певица', 'Поёт у гавани в сумерках', '🎤', 'epic', 'none', 0, 'Вечер в Сан-Викторе'),
    ('dzhulia', 'Джулия', 'певица из Неаполя', 'Выступает в вечернем дворике', '🎶', 'epic', 'none', 0, 'Вечер в Сан-Викторе'),
    ('amara', 'Амара', 'танцовщица', 'Репетирует на солнечной площади', '💃', 'rare', 'none', 0, 'Вечер в Сан-Викторе'),
    ('viola-bolonya', 'Виола', 'танцовщица из Болоньи', 'Репетирует на террасе над гаванью', '🩰', 'rare', 'none', 0, 'Вечер в Сан-Викторе'),
    ('anastasiya', 'Анастасия Лукьяненко', 'гимнастка из Украины', 'Выступает с обручем, лентой и мячом — и твой игрок тренируется с ней', '🤸\u200d♀️', 'legendary', 'xp_pct', 5, None),
    ('kapoeirist', 'Жуан', 'капоэйрист', 'Показывает капоэйру на площади Сан-Виктора', '🥋', 'rare', 'none', 0, None),
    ('smotritel-mayaka', 'Северину', 'смотритель маяка', 'Полирует линзу маяка перед ночной сменой', '🗼', 'rare', 'none', 0, 'Люди гавани'),
    ('bokser', 'Тиму', 'боксёр', 'Бинтует руки на утренней тренировке', '🥊', 'rare', 'none', 0, None),
    ('spasatel', 'Кайо', 'пляжный спасатель', 'Дежурит у бирюзового прибоя', '🛟', 'common', 'none', 0, None),
    ('vratar', 'Диогу', 'вратарь', 'Достаёт мяч из самой девятки', '🧤', 'epic', 'none', 0, None),
    ('karate', 'Кэндзи', 'мастер карате', 'Ведёт утреннюю тренировку у моря', '🥋', 'epic', 'none', 0, None),
    ('massazh', 'Малай', 'массажистка из Таиланда', 'Восстанавливает игроков после матча', '💆\u200d♀️', 'common', 'none', 0, None),
    ('voditel-tramvaya', 'Октавиу', 'водитель трамвая', 'Везёт болельщиков к освещённому стадиону', '🚋', 'common', 'none', 0, None),
)


def _path(slug: str) -> str:
    return f"residents/town/{slug}.webp"


def upgrade() -> None:
    bind = op.get_bind()
    order = int(bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), 0) FROM town_residents")).scalar_one())
    for slug, name, title, description, icon, rarity, bonus, value, set_name in RESIDENTS:
        if bind.execute(sa.text("SELECT 1 FROM town_residents WHERE image_path = :p"), {"p": _path(slug)}).first():
            continue
        order += 1
        bind.execute(sa.text(
            "INSERT INTO town_residents (name, title, description, icon, image_path, rarity, bonus, bonus_value, set_name, "
            "drop_weight, is_pack_droppable, is_active, sort_order, created_at, updated_at) VALUES "
            "(:name, :title, :d, :icon, :image, :rarity, :bonus, :value, :set, 100, true, true, :order, now(), now())"
        ), {"name": name, "title": title, "d": description, "icon": icon, "image": _path(slug), "rarity": rarity,
            "bonus": bonus, "value": value, "set": set_name, "order": order})


def downgrade() -> None:
    bind = op.get_bind()
    for slug, *_ in RESIDENTS:
        # Residents nobody holds yet; a held one stays (the admin can switch it off).
        bind.execute(sa.text(
            "DELETE FROM town_residents WHERE image_path = :p "
            "AND NOT EXISTS (SELECT 1 FROM user_town_residents u WHERE u.resident_id = town_residents.id)"
        ), {"p": _path(slug)})
