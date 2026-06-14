# Stage 1: install dependencies (shared base)
FROM python:3.12-slim-bookworm AS deps
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: production image (no dev tools, minimal footprint)
FROM deps AS production
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: dev image (hot-reload; extends deps, source mounted via volume at runtime)
FROM deps AS dev
RUN pip install --no-cache-dir watchfiles
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000 8501
CMD ["uvicorn", "app.api.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
