# Образ бота (aiohttp + vkbottle). Сборка мини-аппа и Caddy — отдельный
# образ, см. Dockerfile.caddy.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Зависимости отдельным слоем — кэш не сбрасывается, пока requirements.txt
# не менялся (код меняется куда чаще).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# logs/ создаётся ДО chown: на неё монтируется том, а новый именованный том
# Docker заполняет содержимым и ВЛАДЕЛЬЦЕМ папки из образа. Без этого том
# достался бы root, и бот под appuser не смог бы писать в него ни строки.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chmod +x entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
