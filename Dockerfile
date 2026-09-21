FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tzdata first: rarely changes, so code edits never re-run apt
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Dependencies next so code edits do not bust the pip layer either
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Runs as the uid/gid given by compose (see PUID/PGID), so the bind-mounted
# data directory stays writable. Nothing here needs root.
RUN mkdir -p /app/data && chmod 777 /app/data

CMD ["python", "-m", "app.main"]
