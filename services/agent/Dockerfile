FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so pods start without any download.
ENV EMBEDDING_CACHE_DIR=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')" \
    && chmod -R a+rX /opt/fastembed

COPY app ./app
COPY data ./data

# Numeric user id so Kubernetes can enforce runAsNonRoot.
USER 10001

# Links the GHCR package to the repository.
LABEL org.opencontainers.image.source="https://github.com/sarvagna23/ai-agent-platform"

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
