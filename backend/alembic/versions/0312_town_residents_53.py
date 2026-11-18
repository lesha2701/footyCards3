"""«Жители»: 52 new residents — special forces and pilots, sportswomen by
the sea, the club's office (stadium, finance, sport and general directors,
the agent, fans' directors, scouts, media), scientists and the archive,
factory and craft masters, the airport and the harbour (pictures in
static/residents/town). Legendary: Ева, the football agent (+15 coins a
day), and Элена, the general director (+3 % rent). New sets «Сила и
отвага», «Спорт у моря», «Штаб клуба», «Голос трибун», «Наука и архив»,
«Город мастеров» and «Аэропорт Сан-Виктора»; no existing set grows, so no
completed set breaks. Inserted only where the picture is not in the
catalog yet, after the admin's own residents.

Revision ID: 0312
Revises: 0311
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0312"
down_revision: Union[str, None] = "0311"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug, name, title, description, icon, rarity, bonus, bonus value, set
RESIDENTS = (
    ('rafael-specnaz', 'Рафаэл', 'ветеран спецназа', 'Проверяет периметр стадиона перед дерби', '🪖', 'epic', 'none', 0, 'Сила и отвага'),
    ('andre-pilot', 'Андре', 'пилот истребителя', 'Проносится над стадионом на открытии сезона', '✈️', 'epic', 'none', 0, 'Сила и отвага'),
    ('brunu-strongmen', 'Бруну', 'стронгмен', 'Тащит грузовик с клубными флагами по набережной', '🏋️', 'rare', 'none', 0, 'Сила и отвага'),
    ('migel-vertolet', 'Мигел', 'пилот спасательного вертолёта', 'Дежурит над побережьем в штормовую погоду', '🚁', 'epic', 'none', 0, 'Сила и отвага'),
    ('mateush-soldat', 'Матеуш', 'солдат', 'Несёт флаг города на параде в день матча', '🎖️', 'rare', 'none', 0, 'Сила и отвага'),
    ('klara-baidarka', 'Клара', 'байдарочница', 'Тренируется в бухте на рассвете', '🛶', 'common', 'none', 0, 'Спорт у моря'),
    ('inesh-skeit', 'Инеш', 'скейтбордистка', 'Катается на площади у фонтана с мячом', '🛹', 'common', 'none', 0, 'Спорт у моря'),
    ('maia-tennis', 'Майя', 'теннисистка', 'Отрабатывает подачу на корте у моря', '🎾', 'rare', 'none', 0, 'Спорт у моря'),
    ('sofia-velo', 'София', 'велосипедистка', 'Поднимается в гору к старому маяку', '🚴\u200d♀️', 'common', 'none', 0, 'Спорт у моря'),
    ('nora-sprint', 'Нора', 'спринтерка', 'Бьёт рекорд города на стометровке', '🏃\u200d♀️', 'rare', 'none', 0, 'Спорт у моря'),
    ('lara-skaly', 'Лара', 'скалолазка', 'Покоряет утёс над пляжем', '🧗\u200d♀️', 'rare', 'none', 0, 'Спорт у моря'),
    ('amara-basket', 'Амара', 'баскетболистка', 'Забрасывает трёхочковый на уличной площадке', '🏀', 'common', 'none', 0, 'Спорт у моря'),
    ('beatris-fehtovanie', 'Беатрис', 'фехтовальщица', 'Готовится к турниру на шпагах', '🤺', 'epic', 'none', 0, 'Спорт у моря'),
    ('joana-roller', 'Жоана', 'роллерша', 'Мчится по набережной на роликах', '🛼', 'common', 'none', 0, 'Спорт у моря'),
    ('marina-pryzhki', 'Марина', 'прыгунья в воду', 'Прыгает с вышки над бирюзовой водой', '🤽\u200d♀️', 'rare', 'none', 0, 'Спорт у моря'),
    ('vasku-stadion', 'Васко', 'директор стадиона', 'Готовит арену к аншлагу', '🏟️', 'epic', 'none', 0, 'Штаб клуба'),
    ('sofia-finansy', 'София', 'финансовый директор', 'Сводит бюджет клуба до последней монеты', '📊', 'rare', 'none', 0, 'Штаб клуба'),
    ('rui-sport', 'Руй', 'спортивный директор', 'Подбирает новичков для основы', '📋', 'rare', 'none', 0, 'Штаб клуба'),
    ('elena-gendirektor', 'Элена', 'генеральный директор', 'Ведёт клуб к большим трофеям — и аренда в городе растёт', '👩\u200d💼', 'legendary', 'rent_pct', 3, 'Штаб клуба'),
    ('leonor-pomoshnica', 'Леонор', 'помощница президента', 'Помнит расписание президента наизусть', '🗂️', 'common', 'none', 0, 'Штаб клуба'),
    ('duarte-strategiya', 'Дуарте', 'советник по стратегии', 'Рисует план клуба на пять сезонов вперёд', '♟️', 'rare', 'none', 0, 'Штаб клуба'),
    ('kamila-fany', 'Камила', 'директор по работе с болельщиками', 'Встречает фанатов у ворот стадиона', '📣', 'rare', 'none', 0, 'Голос трибун'),
    ('tomash-skaut', 'Томаш', 'руководитель скаутской службы', 'Находит талант на дворовом поле', '🔭', 'epic', 'none', 0, 'Штаб клуба'),
    ('marta-fany', 'Марта', 'директор по работе с болельщиками', 'Раздаёт шарфы детям на трибуне', '🧣', 'common', 'none', 0, 'Голос трибун'),
    ('yumi-fany', 'Юми', 'директор по работе с болельщиками', 'Устраивает фанатам встречу с командой', '🎌', 'rare', 'none', 0, 'Голос трибун'),
    ('lusia-vyezdy', 'Лусия', 'координатор выездов команды', 'Отправляет автобус команды точно по графику', '🧳', 'common', 'none', 0, 'Голос трибун'),
    ('gabriel-media', 'Габриэл', 'продюсер клубных медиа', 'Снимает закулисье матча для клубного канала', '🎬', 'epic', 'none', 0, 'Голос трибун'),
    ('manuel-fizika', 'Мануэл', 'профессор спортивной физики', 'Считает траекторию идеального штрафного', '🧮', 'epic', 'none', 0, 'Наука и архив'),
    ('tereza-biomehanika', 'Тереза', 'профессор биомеханики', 'Разбирает технику удара по кадрам', '🦴', 'rare', 'none', 0, 'Наука и архив'),
    ('joakim-arhiv', 'Жоаким', 'хранитель клубного архива', 'Бережёт мяч первого в истории гола клуба', '📚', 'rare', 'none', 0, 'Наука и архив'),
    ('ingrid-forma', 'Ингрид', 'дизайнер клубной формы', 'Рисует форму к новому сезону', '👕', 'epic', 'none', 0, 'Наука и архив'),
    ('bentu-agronom', 'Бенту', 'агроном стадиона', 'Выращивает идеальный газон к дерби', '🌾', 'common', 'none', 0, 'Наука и архив'),
    ('eva-agent', 'Ева', 'футбольный агент', 'Закрывает сделки быстрее всех в лиге — и каждый день приносит монеты', '🤝', 'legendary', 'daily_coins', 15, 'Штаб клуба'),
    ('adriana-yurist', 'Адриана', 'юристка клуба', 'Проверяет каждый пункт контракта', '⚖️', 'rare', 'none', 0, 'Штаб клуба'),
    ('samuel-sponsory', 'Самуэл', 'директор по спонсорству', 'Подписывает спонсора на форму', '💼', 'rare', 'none', 0, 'Штаб клуба'),
    ('mafalda-svarka', 'Мафалда', 'сварщица', 'Варит каркас новой трибуны', '👩\u200d🏭', 'common', 'none', 0, 'Город мастеров'),
    ('artur-tokar', 'Артур', 'токарь', 'Вытачивает детали для табло стадиона', '⚙️', 'common', 'none', 0, 'Город мастеров'),
    ('renata-zavod', 'Рената', 'инженер завода', 'Запускает линию, где делают мячи', '🏭', 'rare', 'none', 0, 'Город мастеров'),
    ('nunu-aviadispetcher', 'Нуну', 'авиадиспетчер', 'Сажает самолёт с командой гостей', '🗼', 'rare', 'none', 0, 'Аэропорт Сан-Виктора'),
    ('salma-aeroport', 'Сальма', 'сотрудница наземной службы аэропорта', 'Встречает борт с болельщиками', '🦺', 'common', 'none', 0, 'Аэропорт Сан-Виктора'),
    ('diogu-kapitan', 'Диогу', 'командир пассажирского самолёта', 'Везёт команду на выездной матч', '👨\u200d✈️', 'epic', 'none', 0, 'Аэропорт Сан-Виктора'),
    ('alisa-styuardessa', 'Алиса', 'стюардесса', 'Угощает игроков кофе на борту', '💺', 'common', 'none', 0, 'Аэропорт Сан-Виктора'),
    ('enrike-instrumenty', 'Энрике', 'реставратор музыкальных инструментов', 'Чинит барабан фанатского сектора', '🥁', 'rare', 'none', 0, 'Город мастеров'),
    ('petra-stroitel', 'Петра', 'инженер-строитель', 'Проверяет чертежи новой трибуны', '🏗️', 'rare', 'none', 0, 'Город мастеров'),
    ('amir-konditer', 'Амир', 'кондитер', 'Печёт торт в виде мяча к юбилею клуба', '🎂', 'common', 'none', 0, 'Город мастеров'),
    ('daliya-pochta', 'Далия', 'почтальон', 'Разносит письма болельщиков игрокам', '✉️', 'common', 'none', 0, None),
    ('oskar-velomehanik', 'Оскар', 'веломеханик', 'Перебирает велосипед курьера', '🔧', 'common', 'none', 0, 'Город мастеров'),
    ('fatima-keramika', 'Фатима', 'мастер керамики', 'Лепит кубок из глины', '🏺', 'rare', 'none', 0, 'Город мастеров'),
    ('silviu-mayak', 'Силвиу', 'смотритель маяка', 'Зажигает огонь маяка в сумерках', '🔦', 'common', 'none', 0, None),
    ('leandru-buksir', 'Леандру', 'капитан портового буксира', 'Заводит в гавань лайнер с туристами', '⛴️', 'rare', 'none', 0, None),
    ('mei-florist', 'Мэй', 'флорист', 'Собирает букет для чемпионов', '💐', 'common', 'none', 0, None),
    ('eliza-veterinar', 'Элиза', 'ветеринар', 'Лечит щенка, который сбежал на поле', '🐶', 'common', 'none', 0, None),
)

def _path(slug: str) -> str:
    return f"residents/town/{slug}.webp"


MATILDE = "Зовёт сыграть ещё одну: раз в день +1 попытка с наградой в одной мини-игре на твой выбор, пока живёт в районе"


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
    # Матилде: players asked what she gives — the card now says it plainly.
    bind.execute(sa.text("UPDATE town_residents SET description = :d WHERE image_path = :p"), {"d": MATILDE, "p": _path("matilde")})


def downgrade() -> None:
    bind = op.get_bind()
    for slug, *_ in RESIDENTS:
        # Residents nobody holds yet; a held one stays (the admin can switch it off).
        bind.execute(sa.text(
            "DELETE FROM town_residents WHERE image_path = :p "
            "AND NOT EXISTS (SELECT 1 FROM user_town_residents u WHERE u.resident_id = town_residents.id)"
        ), {"p": _path(slug)})
