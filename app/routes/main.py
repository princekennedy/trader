from flask import Blueprint, render_template
from app.models import ExtractionJob, Candle, Strategy

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def dashboard():
    total_jobs = ExtractionJob.query.count()
    total_candles = Candle.query.count()
    completed = ExtractionJob.query.filter_by(status="completed").count()
    strategies = Strategy.query.count()

    recent_jobs = (
        ExtractionJob.query
        .filter_by(status="completed")
        .order_by(ExtractionJob.created_at.desc())
        .limit(5)
        .all()
    )

    avg_quality = 0
    if completed:
        result = ExtractionJob.query.with_entities(
            ExtractionJob.quality_score
        ).filter(
            ExtractionJob.status == "completed",
            ExtractionJob.quality_score.isnot(None)
        ).all()
        if result:
            avg_quality = round(sum(r[0] or 0 for r in result) / len(result), 2)

    return render_template(
        "dashboard.html",
        total_jobs=total_jobs,
        total_candles=total_candles,
        avg_quality=avg_quality,
        strategies=strategies,
        recent_jobs=recent_jobs,
    )


@main_bp.route("/settings")
def settings():
    return render_template("settings.html")
