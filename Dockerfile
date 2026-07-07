# ============================================
# Stage 1: Build Tailwind CSS assets
# ============================================
FROM node:20-alpine AS tailwind-builder

WORKDIR /app

COPY package.json tailwind.config.js ./
COPY app/static/css/input.css ./app/static/css/input.css

RUN npm install && \
    npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/output.css --minify

# ============================================
# Stage 2: Python dependencies
# ============================================
FROM python:3.12-slim AS python-builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn==23.0.0

# ============================================
# Stage 3: Final production image
# ============================================
FROM python:3.12-slim

WORKDIR /app

# Install runtime system dependencies (if any needed, e.g. for Pillow)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libjpeg62-turbo libwebp7 && \
    rm -rf /var/lib/apt/lists/*

# Copy Python site-packages from builder
COPY --from=python-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy application code
COPY run.py ./
COPY app/ ./app/

# Copy pre-built Tailwind CSS from builder
COPY --from=tailwind-builder /app/app/static/css/output.css ./app/static/css/output.css

# Create data and uploads directories
RUN mkdir -p /app/data /app/uploads

# Environment variables (defaults – override via docker-compose or -e flags)
ENV FLASK_ENV=production
ENV FLASK_APP=run.py
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Run migrations then start Gunicorn
COPY migrations/ ./migrations/
CMD flask db upgrade && gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 run:app