from flask import Blueprint, render_template, jsonify
from app.models import ExtractionJob, Candle, Strategy

data_bp = Blueprint("data", __name__, url_prefix="/data")


@data_bp.route("/")
def index():
    jobs = ExtractionJob.query.order_by(ExtractionJob.created_at.desc()).all()
    strategies = Strategy.query.all()
    return render_template("data.html", jobs=jobs, strategies=strategies)


@data_bp.route("/api/jobs")
def api_jobs():
    jobs = ExtractionJob.query.order_by(ExtractionJob.created_at.desc()).all()
    return jsonify([
        {
            "id": j.id,
            "filename": j.filename,
            "symbol": j.symbol,
            "timeframe": j.timeframe,
            "status": j.status,
            "candle_count": j.candle_count,
            "quality_score": j.quality_score,
            "created_at": str(j.created_at),
        }
        for j in jobs
    ])


@data_bp.route("/api/job/<int:job_id>/candles")
def api_candles(job_id):
    candles = Candle.query.filter_by(job_id=job_id).order_by(Candle.index).all()
    return jsonify([
        {
            "index": c.index,
            "direction": c.direction,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "body": c.body,
            "upper_wick": c.upper_wick,
            "lower_wick": c.lower_wick,
        }
        for c in candles
    ])
