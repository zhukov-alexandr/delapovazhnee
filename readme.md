# delapovazhnee.ru — раннер + пресейв A/B

Браузерная игра-раннер (пляжный закат, пиксель-ретро) для пресейва нового сингла группы
«Дела поважнее», плюс бэкенд со сбором A/B-статистики. Один сервер на FastAPI раздаёт
игру, лендинг, API событий, редирект пресейва, QR и админку.

## Стек

Python 3.12 · FastAPI · Uvicorn · stdlib `sqlite3` (без ORM) · Jinja2 · `qrcode[pil]`.
Игра — ванильный JS (canvas 2D, ES-модули). Тесты: `pytest` (бэкенд) + headless-`node` (игровая логика).

## Быстрый старт

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt      # runtime + тесты (или requirements.txt только runtime)

cp .env.example .env                      # заполнить секреты (см. ниже)
uvicorn main:app --host 0.0.0.0 --port 8000
```

Открыть:
- `/` — **игра** (открывается сразу);
- `/home` — **лендинг** (старый сайт);
- `/tickets` — **билеты**: все концерты тура, у каждого своя кнопка;
- `/admin` — **дашборд/админка** (логин из `.env`).

## Переменные окружения (`.env`)

| Переменная | Назначение |
|---|---|
| `PRESAVE_URL` | целевая ссылка пресейва (302 из `/go/presave`). **Обязательно** задать. |
| `ADMIN_USER`, `ADMIN_PASS` | доступ к `/admin` |
| `SECRET_KEY` | подпись cookie-сессии админа (сгенерировать длинную случайную строку) |
| `PUBLIC_BASE_URL` | (опц.) абсолютный базовый URL для QR; иначе берётся из запроса |
| `DB_PATH` | (опц.) путь к sqlite, по умолчанию `db/stats.db` |

Сгенерировать `SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## A/B-тест пресейва

- Вариант назначает **сервер** при первом заходе на `/` (случайно 50/50), кладёт в cookie
  `dp_variant`/`dp_sid` (липнет к сессии) и вшивает в страницу.
- **Вариант A** — CTA (QR + кнопка «Сделать пресейв») на **стартовом экране**.
- **Вариант B** — CTA на экране **Game Over**.
- И кнопка, и QR ведут через `GET /go/presave?v={A|B}&src={button|qr}&sid=…` → сервер логирует
  `cta_click` → 302 на `PRESAVE_URL`. QR кодирует этот же URL (`src=qr`, вшитый вариант) — скан
  с другого устройства атрибутируется по варианту в QR.
- События (`POST /api/event`): `visit`, `game_start`, `game_over{score}`, `cta_view`
  (+ `cta_click` логируется сервером в `/go/presave`).

## Метрики (дашборд `/admin`)

По каждому варианту рядом: уникальные сессии, показы/клики CTA (+ разбивка button/qr), **CVR**,
игр начато/завершено, средний счёт, график по дням. Сравнение вариантов **устойчиво к малой
выборке**: байесовская вероятность `P(CVR_B > CVR_A)` (Beta-Binomial) как основная метрика +
точный тест Фишера (p-value). Экспорт сырых событий — CSV (`/admin/export.csv`).

## Куда класть ассеты

- **Музыка:** `static/assets/music.mp3` (loop, громкость 0.5, старт после первого касания,
  есть mute). Пока файла нет — игра работает без музыки.
- **Спрайты игры:** арт рисуется процедурно по умолчанию; чтобы заменить на PNG — положить картинки в готовые папки для дроп-ина:
  - `static/sprites/characters/` — `char1.png`…`char4.png`, персонажи выбора на стартовом экране.
    Порядковый номер в имени файла (1..4) соответствует `charIndex` (0..3) в коде: `char1.png` →
    `charIndex=0`, …, `char4.png` → `charIndex=3`. Точка подмены в `sprites.js` — ключи
    `images["char_0"]`…`images["char_3"]` (т.е. `char<N+1>.png` → ключ `char_<N>`).
  - `static/sprites/items/` — `item1.png`, `item2.png`, `item3.png` (столько видов, сколько
    `GAME.ITEM_KINDS`, сейчас 3). Аналогично: `item1.png` → `kind=0` → ключ `images["item_0"]`,
    `item2.png` → `kind=1` → `images["item_1"]`, `item3.png` → `kind=2` → `images["item_2"]`.
  - Файлы в обеих папках подхватываются автоматически **при перезагрузке страницы**: `boot.js` вызывает
    `loadSprites()` с манифестом, который сопоставляет эти пути с ключами `char_0..char_3` / `item_0..item_2`.
    Отсутствующие файлы (404/onerror) тихо оставляют процедурный фолбэк, не ломая игру.
- **Обложка для лендинга:** положить файл обложки прошлого сингла в `static/home/` (напр.
  `cover.jpg`) — нужен для редизайна лендинга (см. дизайн-док).

## Три визуальные айдентики

Не унифицированы (см. `docs/superpowers/specs/2026-07-01-visual-directions.md`):
- **Игра** — летний закатный пиксель (PS1/Sega), кириллический пиксель-шрифт;
- **Лендинг** — в стиле обложки прошлого сингла (полуночно-синий, рваная бумага, рукопись);
- **Админка** — обычная, без излишеств.

## Тесты

```bash
. .venv/bin/activate
python -m pytest -v                       # бэкенд (events, presave, qr, метрики, админка)
node tests/js/selftest.node.mjs           # чистая игровая логика (физика/препятствия/A/B)
node tests/js/gamestate.smoke.mjs         # прогресс игры (коллизия→game over, счёт)
node tests/js/sprites.smoke.mjs           # рендер-функции (no-crash + swap-point)
```

В браузере: `/?selftest=1` — прогоняет ассерты игровой логики и показывает баннер PASS/FAIL.

## Структура

```
main.py                # FastAPI: роуты, монтирование статики, инициализация схемы
server/                # config, ab (50/50), db, metrics (Bayes+Fisher), qr, api, admin
templates/             # game.html, home.html (лендинг), tickets.html (билеты), admin_login.html, admin.html
static/js/             # config, physics, obstacles, ab, gamestate, sprites, game, audio, boot, selftest
static/css/            # game.css (закат), admin.css (простой)
static/home/           # ассеты лендинга и страницы билетов (site.css, site.js, афиши, фавиконки)
tests/                 # pytest (бэкенд) + tests/js (node)
db/                    # sqlite (создаётся автоматически; в .gitignore)
```
