# Backend image — FastAPI on uvicorn.
FROM python:3.12-slim

# Faster, quieter Python in a container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install deps first so this layer caches unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source. In local dev, compose bind-mounts over this for hot reload.
COPY app ./app

EXPOSE 8000

# Production default. Compose overrides this with --reload for local dev.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
