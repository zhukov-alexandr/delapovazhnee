# Деплой на VDS — Docker + Caddy (по тэгу `v*`)

Пуш тэга вида `v*` (напр. `v1.0.0`, `v0.3`, `v2`) → GitHub Actions:
**тесты → сборка образа → push в GHCR → сервер `docker compose pull && up -d`** (`.github/workflows/deploy.yml`).
Сборка тяжёлого образа идёт на раннере GitHub, а VDS только тянет готовый — поэтому 1–2 ГБ RAM хватает.
Обычные push/PR — только тесты (`.github/workflows/ci.yml`).

Сейчас отдаётся по **HTTP на IP** (без домена). Caddy стоит перед приложением; при появлении домена —
одна строка в `deploy/Caddyfile` включает авто-HTTPS.

## 0. Требования к серверу

**1 CPU / 2 GB RAM / 10 GB диск / 1 TB трафик** — комфортно (1 ГБ тоже потянет, 2 — с запасом под Docker).
Нужен только Docker (ставит `bootstrap-vds.sh`). Держи музыку сжатой (~3–4 МБ) — основной расход трафика.
ОС: Ubuntu 26.04.

## 1. GitHub Secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Что |
|---|---|
| `VDS_HOST` | IP сервера |
| `VDS_USER` | ssh-пользователь деплоя (`deploy`) |
| `VDS_PATH` | каталог приложения, напр. `/opt/delapovazhnee` |
| `VDS_SSH_KEY` | **приватный** ssh-ключ деплоя (весь файл) |
| `VDS_SSH_PORT` | (опц.) порт ssh, если не 22 |
| `GHCR_PAT` | classic PAT с областью **`read:packages`** — сервер тянет приватный образ из GHCR |

`GHCR_PAT`: GitHub → Settings → Developer settings → **Personal access tokens (classic)** → Generate →
отметить только `read:packages`. (Пуш образа делает CI сам через встроенный `GITHUB_TOKEN`.)

## 2. Разовая настройка сервера (один раз)

Репозиторий на VDS не клонируется — скрипт надо доставить самому. Со **своей машины** (репо склонирован
локально), под пользователем с root/sudo на сервере:
```bash
scp deploy/bootstrap-vds.sh root@IP:/root/           # или your_sudo_user@IP:~/
ssh root@IP 'bash /root/bootstrap-vds.sh'            # не под root? → ssh you@IP 'sudo bash ~/bootstrap-vds.sh'
# Альтернатива только для ПУБЛИЧНОГО репо:
#   curl -fsSLO https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/bootstrap-vds.sh && sudo bash bootstrap-vds.sh
```
Запускается под root/sudo (ставит Docker, юзера — `deploy` ещё нет). Скрипт ставит Docker, создаёт юзера
`deploy` (+ группа docker), каталог `/opt/delapovazhnee` с подкаталогами под ассеты, заготовку `.env`,
и swap 2G. После него:

1. **Публичный** деплой-ключ → `/home/deploy/.ssh/authorized_keys` (`chmod 600`, владелец `deploy`).
   Проще всего со своей машины: `ssh-copy-id -i ~/.ssh/dp-deploy.pub deploy@IP`.
2. Впиши реальные значения в `/opt/delapovazhnee/.env` (`PRESAVE_URL`, `ADMIN_USER`, `ADMIN_PASS`,
   `SECRET_KEY`; при желании `PUBLIC_BASE_URL=http://IP` для QR).
3. Проверь ssh: `ssh -i ~/.ssh/dp-deploy deploy@IP 'docker ps'`.

## 3. Ассеты на VDS (переживают деплой)

Большие бинарники кладутся **на сервер** в смонтированные каталоги (в образ не пекутся, обновление их не трёт):

- `/opt/delapovazhnee/static/assets/music.mp3`
- `/opt/delapovazhnee/static/sprites/characters/char1.png … char4.png`
- `/opt/delapovazhnee/static/sprites/items/item1.png … item3.png`

БД (`sqlite`) живёт в docker-volume `dbdata` и тоже переживает пересоздание контейнера.

## 4. Выкатка версии

```bash
git tag v1.0.0 && git push origin v1.0.0
```
Actions прогонит тесты, соберёт образ `ghcr.io/<owner>/<repo>:v1.0.0`, сервер его подтянет и перезапустит.
Откат — пуш тега на прошлом коммите (образ той версии уже в GHCR).

## 5. Домен + HTTPS (обязательно для рабочего пресейва!)

Без домена/HTTPS пресейв по шлюзовым сервисам band.link (Яндекс/VK/КИОН) не
финализируется — band.link принимает `redirectUrl` только как публичный
HTTPS-URL с доменом и на `http`/`localhost`/голом IP отдаёт **ERROR_1009**.
(Spotify идёт мимо шлюза и работает и на IP; Apple — отдельная история.)

Шаги (Caddyfile уже env-driven, править его не нужно):

1. A-запись домена → на IP VDS; порты 80 и 443 открыты.
2. В `.env` на сервере добавить:
   ```
   SITE_ADDRESS=твой-домен.ру
   PUBLIC_BASE_URL=https://твой-домен.ру
   ```
3. `docker compose up -d` (или пуш нового тега) — Caddy сам выпустит и продлит
   сертификат Let's Encrypt; сайт станет отдаваться по HTTPS.
4. Проверить пресейв: Яндекс/VK/КИОН должны докручиваться до «Сохранено» без
   ERROR_1009.

## 6. Полезное на сервере

```bash
cd /opt/delapovazhnee
docker compose logs -f app        # логи приложения
docker compose ps                 # статус
docker compose restart app        # перезапуск
docker run --rm -v delapovazhnee_dbdata:/d -v "$PWD":/b alpine cp /d/stats.db /b/stats.db.bak  # бэкап БД
```
