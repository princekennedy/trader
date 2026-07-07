from flask import Blueprint, render_template, jsonify, g
from flask_login import login_required
from app.models import ExtractionJob, Candle, Strategy
from app.utils.auth import org_required

data_bp = Blueprint("data", __name__, url_prefix="/data")


@data_bp.route("/")
@login_required
@org_required
def index():
    org = g.current_org
    jobs = ExtractionJob.query.filter_by(organization_id=org.id).order_by(
        ExtractionJob.created_at.desc()
    ).all()
    strategies = Strategy.query.filter_by(organization_id=org.id).all()
    return render_template("data.html", jobs=jobs, strategies=strategies)


@data_bp.route("/api/jobs")
@login_required
@org_required
def api_jobs():
    org = g.current_org
    jobs = ExtractionJob.query.filter_by(organization_id=org.id).order_by(
        ExtractionJob.created_at.desc()
    ).all()
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
@login_required
@org_required
def api_candles(job_id):
    org = g.current_org
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first_or_404()
    candles = Candle.query.filter_by(job_id=job.id).order_by(Candle.index).all()
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
