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

# Alembic migrations ship in the same image as the app, so migration code and
# app code can never drift apart. Run them with: alembic upgrade head
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

EXPOSE 8000

# Production default. Compose overrides this with --reload for local dev.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
