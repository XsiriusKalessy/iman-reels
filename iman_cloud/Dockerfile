# Servidor de la IA incluida (api.imanreels.com). Solo recibe texto: nunca vídeos.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY iman ./iman
COPY iman_cloud ./iman_cloud
RUN pip install --no-cache-dir fastapi uvicorn anthropic openai fonttools pillow python-multipart \
    && pip install --no-cache-dir --no-deps .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn iman_cloud.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
