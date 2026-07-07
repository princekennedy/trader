# TradingView Candlestick Extractor

Reverse-engineer OHLCV datasets from TradingView candlestick chart images using computer vision, with a multi-user Flask web UI, per-organization data isolation, and YOLO-based AI detection.

## Features

- **Chart Extraction** — Upload candlestick chart screenshots; the system detects individual candles using scipy peak-finding on column-density histograms, classifies bullish/bearish, and computes relative OHLC, body, and wick values.
- **Data Manager** — Browse all extracted datasets with a three-tab preview modal (original image, candle table, TradingView Lightweight Chart).
- **AI Analysis** — Upload chart images for YOLO object detection (pre-trained COCO model).
- **Multi-tenant** — Organizations with role-based membership (admin/member), per-org data isolation on all jobs and strategies.
- **Authentication** — Register, login, logout, forgot-password stub; Flask-Login session management.
- **Storage** — MinIO (S3-compatible) with automatic fallback to local filesystem when MinIO is unavailable.
- **Export** — Download extracted candle data as JSON.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.1 |
| Database | PostgreSQL 16 (SQLite for local dev) |
| ORM | SQLAlchemy 3.1 + Flask-Migrate (Alembic) |
| Auth | Flask-Login, per-org scoping |
| Frontend | Tailwind CSS, Alpine.js 3.14 |
| Charts | TradingView Lightweight Charts 4.2 |
| CV | OpenCV 4.13, scipy 1.17 |
| AI | Ultralytics YOLO 8.4 |
| Storage | MinIO (S3-compatible) |
| Infra | Docker Compose, Gunicorn |

## Project Structure

```
trading/
├── app/
│   ├── __init__.py          # App factory, DB, migrate, login manager
│   ├── models/
│   │   └── __init__.py      # User, Organization, ExtractionJob, Candle, Strategy
│   ├── routes/
│   │   ├── __init__.py      # Blueprint registration
│   │   ├── auth.py          # Login, register, logout, forgot
│   │   ├── org.py           # Org CRUD, member management, org switching
│   │   ├── main.py          # Dashboard, settings
│   │   ├── charts.py        # Upload, extract, export, reprocess, delete
│   │   ├── data.py          # Dataset browser + JSON API endpoints
│   │   └── ai.py            # YOLO upload-and-detect page
│   ├── templates/           # Jinja2 templates (13 files)
│   │   ├── base.html        # Sidebar layout, auth-aware nav
│   │   ├── auth_login.html  # Standalone auth pages
│   │   ├── charts.html      # Upload form + job history + preview modal
│   │   ├── data.html        # Dataset list + three-tab preview modal
│   │   └── ...
│   ├── utils/
│   │   ├── auth.py          # login_required, org_required decorators
│   │   ├── detector.py      # YOLO wrapper (lazy cv2/ultralytics import)
│   │   ├── extractor.py     # ChartExtractor: image → OHLCV pipeline
│   │   └── storage.py       # MinioStorage + LocalStorage + factory
│   └── static/
│       └── css/
│           └── input.css    # Tailwind CSS source
├── migrations/              # Alembic migrations
├── Dockerfile               # Multi-stage (Tailwind builder + Python runtime)
├── docker-compose.yml       # web + minio + postgres
├── .env                     # Environment config
├── requirements.txt         # Python dependencies
└── run.py                   # Entry point
```

## Quick Start

### Local Development

```bash
# 1. Clone and enter the project
git clone <repo> && cd trading

# 2. Create a virtual environment
python -m venv venv && source venv/bin/activate  # or .\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (use SQLite for local dev)
export DATABASE_URL=sqlite:///trading.db
export MINIO_ENDPOINT=""  # disable MinIO, use local filesystem

# 5. Apply migrations
flask db upgrade

# 6. Run
flask run
```

Visit `http://localhost:5000` — register an account, create an organization, then upload chart images.

### Docker Compose (Production-like)

```bash
# Start all services (PostgreSQL, MinIO, web app)
docker compose up --build -d

# The app is available at http://localhost:5000
```

Services:
- **web** — Flask app on port 5000
- **minio** — S3-compatible object storage (console: port 9001)
- **db** — PostgreSQL 16 on port 5432

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://trading:trading@localhost:5432/trading` | Database connection string |
| `SECRET_KEY` | `dev` | Flask secret key |
| `UPLOAD_FOLDER` | `./uploads` | Local file upload directory |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO server (empty = local storage) |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `trading-charts` | MinIO bucket name |

## Migrations

Database migrations use Flask-Migrate (Alembic). The Docker `CMD` runs `flask db upgrade` automatically on container start.

```bash
# After changing models, generate a new migration
flask db migrate -m "description_of_change"

# Apply pending migrations
flask db upgrade

# Roll back one step
flask db downgrade
```

## Models

All data tables inherit `AuditMixin` providing `created_at`, `updated_at`, `created_by_id`, and `updated_by_id` columns.

| Table | Key Columns | Audit |
|-------|------------|-------|
| `users` | name, email, password_hash, is_active, last_login_at | Yes |
| `organizations` | name, slug, description, owner_id | Yes |
| `user_organizations` | user_id, org_id, role | created_at only |
| `extraction_jobs` | org_id, filename, object_name, symbol, timeframe, status, candle_count, quality_score | Yes |
| `candles` | job_id, index, direction, open/high/low/close, volume, body, wick values, confidence | Yes |
| `strategies` | org_id, name, description, config (JSON), is_active | Yes |

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET/POST | `/auth/login` | No | Login page |
| GET/POST | `/auth/register` | No | Registration |
| GET | `/auth/logout` | No | Logout |
| GET/POST | `/org/create` | Login | Create organization |
| GET | `/org/select` | Login | Organization picker |
| GET | `/org/<id>/switch` | Login | Switch active org |
| GET/POST | `/org/<id>/settings` | Login | Org settings (members) |
| GET/POST | `/charts/` | Login+Org | Upload chart, list jobs |
| GET | `/charts/job/<id>` | Login+Org | Job detail |
| POST | `/charts/job/<id>/reprocess` | Login+Org | Re-extract from image |
| POST | `/charts/job/<id>/delete` | Login+Org | Delete job |
| GET | `/charts/job/<id>/export` | Login+Org | Download JSON |
| GET | `/data/` | Login+Org | Data manager |
| GET | `/data/api/jobs` | Login+Org | Job list (JSON) |
| GET | `/data/api/job/<id>/candles` | Login+Org | Candle data (JSON) |
| GET/POST | `/ai/` | Login+Org | YOLO detection |
| GET | `/` | Login+Org | Dashboard |
| GET | `/settings` | Login+Org | Settings page |

## Extraction Pipeline

1. Image uploaded → stored in MinIO (or local filesystem)
2. `ChartExtractor` loads with OpenCV, converts to grayscale
3. Applies binary threshold + vertical column-density histogram
4. `scipy.signal.find_peaks` locates candle positions
5. For each candle: measures body (open/close) and wicks (high/low)
6. Assigns direction and confidence based on body vs wick ratios
7. Results stored as `ExtractionJob` + `Candle` rows in the database

## License

MIT
