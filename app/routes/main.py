from flask import Blueprint, render_template, g
from flask_login import login_required, current_user
from app.models import ExtractionJob, Candle, Strategy
from app.utils.auth import org_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
@org_required
def dashboard():
    org = g.current_org

    total_jobs = ExtractionJob.query.filter_by(organization_id=org.id).count()
    total_candles = Candle.query.join(ExtractionJob).filter(
        ExtractionJob.organization_id == org.id
    ).count()
    completed = ExtractionJob.query.filter_by(
        organization_id=org.id, status="completed"
    ).count()
    strategies = Strategy.query.filter_by(organization_id=org.id).count()

    recent_jobs = (
        ExtractionJob.query
        .filter_by(organization_id=org.id, status="completed")
        .order_by(ExtractionJob.created_at.desc())
        .limit(5)
        .all()
    )

    avg_quality = 0
    if completed:
        result = ExtractionJob.query.with_entities(
            ExtractionJob.quality_score
        ).filter(
            ExtractionJob.organization_id == org.id,
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
@login_required
@org_required
def settings():
    return render_template("settings.html")
