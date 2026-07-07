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
# Stage 2: Final production image
# ============================================
FROM python:3.12-slim

WORKDIR /app

# Install runtime system dependencies (needed for OpenCV, Pillow, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libjpeg62-turbo \
        libwebp7 \
        libgl1 \
        libxcb1 \
        libxcb-shm0 \
        libxcb-xfixes0 \
        libxcb-shape0 \
        libxcb-render0 \
        libxcb-randr0 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-icccm4 \
        libxcb-sync1 \
        libxcb-xinerama0 \
        libxcb-xkb1 \
        libxcb-render-util0 \
        libxkbcommon0 \
        libxkbcommon-x11-0 \
        libsm6 \
        libice6 \
        libxext6 \
        libxrender1 \
        && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly (avoids multi-stage .so issues)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn==23.0.0

# Copy application code
COPY run.py ./
COPY app/ ./app/

# Copy pre-built Tailwind CSS from builder
COPY --from=tailwind-builder /app/app/static/css/output.css ./app/static/css/output.css

# Copy migrations for flask db upgrade
COPY migrations/ ./migrations/

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
CMD flask db upgrade && gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 run:app