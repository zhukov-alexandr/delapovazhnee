# Образ приложения. Собирается в CI (GitHub Actions) и пушится в GHCR; сервер только тянет.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Зависимости отдельным слоем (кэшируется, пока requirements.txt не меняется).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Код приложения (что НЕ копируется — см. .dockerignore: секреты, БД, тесты, ассеты-биннарники).
COPY . .

# Версия сборки = деплой-тег (build-arg из CI). Читается приложением (APP_VERSION):
# служит cache-buster'ом (?v=) и показывается в углу страницы.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

# Непривилегированный пользователь; каталог БД под именованный volume.
RUN useradd -m app && mkdir -p /app/db && chown -R app /app
USER app

EXPOSE 8000
# --proxy-headers + доверие прокси (Caddy в той же docker-сети): request.base_url берёт
# внешний scheme/host из X-Forwarded-* — корректные абсолютные URL и по IP (http), и по домену (https).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
