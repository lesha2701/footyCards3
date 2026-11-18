# Менеджер: промпты, часть 2 (тренеры и иконки без рамок)

Куда класть: просто скинь папку, я сам сконвертирую в webp и разложу.
Имя файла должно совпадать с кодом из таблицы. Пока картинки нет, игра показывает эмодзи.

---

## 1. Главные тренеры: 12 портретов (`coach_<код>`)

Характер выпадает случайно, когда нанимаешь главного тренера в «Персонале». Портрет показывается:
- в карточке тренера во вкладке «Тактика»;
- в его листе за круглым столом.

### Общий стиль (вставлять в начало каждого промпта)

> Stylized semi-realistic portrait of a football head coach for a premium mobile football manager game, 768×768, square. Head and shoulders, three-quarter view, looking slightly toward the viewer. Painted digital illustration with clean shapes, soft cinematic rim light, warm key light from the left. Background: a softly blurred stadium tunnel / dugout at evening with floodlight bokeh, dark teal-green tones, no readable text, no logos, no club badges, no flags. Same art style and lighting as a set of 12 coach portraits — consistent framing, face fills about 45% of the frame, shoulders cut at the bottom edge. Fictional person, not resembling any real coach.

### Портреты (дописать после общего стиля)

| код | характер | кто на портрете |
|---|---|---|
| `coach_spaniard` | Испанец · «Тики-така» | a slim man in his 40s with short dark hair and a neat stubble, a fitted dark navy cardigan over a white shirt, calm thoughtful expression, one hand gesturing as if explaining a passing pattern |
| `coach_portuguese` | Португалец · «Особенный» | a confident man around 50, swept-back salt-and-pepper hair, sharp dark grey overcoat with the collar up, a knowing half-smile, arms crossed |
| `coach_frenchman` | Француз · «Эстет» | an elegant man in his late 40s with wavy chestnut hair and round tortoiseshell glasses, a camel scarf loosely wrapped, a slight artistic smile |
| `coach_englishman` | Англичанин · «Старая школа» | a broad-shouldered ruddy-faced man in his late 50s, thinning grey hair, a heavy padded touchline coat in dark green, a stern shout-ready expression |
| `coach_german` | Немец · «Машина» | a tall disciplined man in his early 50s with short neat blond-grey hair and rimless glasses, a dark charcoal quilted coach jacket zipped up, a precise focused look, one finger raised as if giving an exact instruction |
| `coach_italian` | Итальянец · «Катеначчо» | a stylish man in his mid 50s with slicked-back dark grey hair and a trimmed beard, a tailored navy suit with an open collar, arms folded, a calm calculating half-smile |
| `coach_strategist` | Стратег · «Шахматист» | a lean bald man in his 50s with a trimmed grey beard, thin-rimmed glasses, a black turtleneck, holding a small tactics tablet, focused calculating look |
| `coach_motivator` | Мотиватор · «Огонь в раздевалке» | an energetic man in his late 30s with a buzz cut, a club tracksuit jacket zipped to the chin, fist raised near the chest, a fiery passionate expression, slight motion in the hair |
| `coach_iron` | Железный · «Дисциплина» | a tall stern woman in her 40s with her hair pulled back tightly, a structured black coach jacket, arms behind her back, an unblinking disciplined look |
| `coach_gambler` | Авантюрист · «Всё или ничего» | a charismatic man in his 40s with longish messy hair and a playful grin, an unbuttoned open-collar shirt under a leather jacket, a coin flipping above his fingers |
| `coach_mentor` | Наставник · «Отец команды» | a kind grey-haired man in his 60s with a warm smile and laugh lines, a knitted sweater over a collared shirt, a whistle on a cord around his neck |
| `coach_pragmatist` | Прагматик · «Результат любой ценой» | a composed woman in her early 40s with a short practical bob, a dark club rain jacket, a notebook in hand, a cool neutral expression |

Национальности есть у шести: Испанец, Португалец, Француз, Англичанин, Немец, Итальянец. Остальные шесть называются по чертам характера. Флагов на портретах нет.

---

## 2. Иконки разделов: новый стиль без рамок и фона

Старые иконки (синяя плитка с золотой рамкой) уходят. Новые — один крупный объект на прозрачном фоне, без плитки и без кружка вокруг. Коды те же, поэтому прислал — и они сразу встанут на место. В интерфейсе я сделал их крупнее.

### Общий стиль (вставлять в начало каждого промпта)

> Premium mobile game icon, 512×512, FULLY TRANSPARENT background (PNG with alpha). ONE bold, simple 3D object only, centered, filling about 85% of the canvas. Glossy stylized 3D render, warm gold and rich color accents, soft top-left light, a subtle soft shadow under the object. NO tile, NO frame, NO circle, NO badge shape, NO background color, NO scene, no text, no letters, no numbers. Clean silhouette readable at 32 px. Same style as a set of football manager icons.

### Главные вкладки

| код | вкладка | объект |
|---|---|---|
| `tab_club` | Клуб | a football club crest shield in deep green and gold with a football in the center |
| `tab_transfers` | Трансферы | two folded football jerseys (one red, one blue) with a gold curved swap arrow between them |
| `tab_office` | Кабинет | a dark brown leather executive briefcase with a gold clasp |
| `tab_staff` | Персонал | a small round wooden boardroom table with three tiny chairs around it, seen from a 3/4 angle |

### Внутри клуба и другие места

| код | где | объект |
|---|---|---|
| `tab_league` | Лига (шаги новичка) | a gold championship trophy cup with two handles |
| `tab_style` | Стиль | a football jersey with a paint brush crossing it |
| `tab_me` | Я игрок | a football boot with a ball next to it |
| `desk_assistant` | стол Алисы | a leather planner with a gold pen clipped to it |
| `desk_analyst` | стол Марка | a tablet showing a rising bar chart |
| `desk_garage` | Гараж (в «Стиле») | a car key with a gold shield-shaped fob |

### Кабинет президента

| код | раздел | объект |
|---|---|---|
| `pres_report` | Отчёт | a document sheet with a pie chart |
| `pres_budget` | Бюджет | an open ledger book with a stack of gold coins on it |
| `pres_bank` | Банк | a classical bank building facade with columns, small and chunky |
| `pres_deals` | Сделки | two hands in a handshake, gold cufflinks |
| `pres_sponsor` | Спонсор | a gold ribbon banner with a blank shield, like a sponsor badge |
| `pres_matchday` | Стадион | a small stadium bowl with floodlights |
| `pres_awards` | Награды | a gold medal on a red-white ribbon |
| `pres_rating` | Рейтинг | a podium with three steps and a star above the top step |
| `pres_exchange` | Биржа | a green candlestick chart arrow going up |

---

## 3. Значки отделов за круглым столом (`dept_*`): без рамки и фона

Сейчас у каждого значка синяя плитка с золотой рамкой. Новые: только символ на прозрачном фоне. Общий стиль тот же, что в разделе 2.

| код | отдел | объект |
|---|---|---|
| `dept_coach` | Тренерский штаб | a gold whistle on a cord lying on a small tactics clipboard |
| `dept_director` | Спортивный департамент | a gold compass next to a tactics clipboard |
| `dept_scout` | Скаутинг | a pair of gold binoculars |
| `dept_academy` | Академия | a football with a small green sprout growing from the top |
| `dept_physio` | Медицинский центр | a gold medical cross with a heartbeat line across it |
| `dept_transport` | Транспортный департамент | a gold-and-navy team coach bus, front 3/4 view |
| `dept_stadium` | Стадион | a small round stadium with a green pitch and four floodlights |
| `dept_press` | Пресс-служба | a gold studio microphone on a short stand |
| `dept_marketing` | Коммерция | a gold megaphone with a few confetti pieces |
| `dept_finance` | Финансы | a round gold vault door with a spoked handle |
