# ShowRec backend — FastAPI
FROM python:3.12-slim

WORKDIR /app/backend

# System deps (none needed beyond pip wheels on 3.12)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent SQLite cache lives on a mounted volume
ENV DB_PATH=/data/showrec_cache.db
RUN mkdir -p /data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
