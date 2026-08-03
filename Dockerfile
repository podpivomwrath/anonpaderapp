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

RUN useradd --create-home --uid 1000 appuser \
    && chmod +x entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
