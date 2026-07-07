import os
import io
import json
import uuid
import mimetypes
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app, send_file, g
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import ExtractionJob, Candle
from app.utils.storage import get_storage, storage_available
from app.utils.auth import org_required

try:
    from app.utils.extractor import ChartExtractor
    EXTRACTOR_AVAILABLE = True
except ImportError:
    ChartExtractor = None
    EXTRACTOR_AVAILABLE = False

charts_bp = Blueprint("charts", __name__, url_prefix="/charts")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
CHART_PREFIX = "charts"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _object_name(filename):
    return f"{CHART_PREFIX}/{uuid.uuid4().hex}_{filename}"


def _upload_to_storage(file_storage, filename):
    storage = get_storage()
    obj_name = _object_name(filename)
    storage.upload_bytes(
        file_storage.read(),
        obj_name,
        content_type=file_storage.content_type or "image/png",
    )
    return obj_name


def _extract_from_storage(object_name):
    storage = get_storage()
    data = storage.download_bytes(object_name)
    extractor = ChartExtractor()
    return extractor.extract_from_bytes(data)


def _set_audit_fields(record):
    if current_user.is_authenticated:
        record.created_by_id = current_user.id


def _set_audit_updated(record):
    if current_user.is_authenticated:
        record.updated_by_id = current_user.id


@charts_bp.route("/", methods=["GET", "POST"])
@login_required
@org_required
def index():
    org = g.current_org

    if request.method == "POST":
        file = request.files.get("chart_image")
        if not file or not file.filename:
            flash("No file selected", "error")
            return redirect(url_for("charts.index"))

        if not allowed_file(file.filename):
            flash("File type not allowed", "error")
            return redirect(url_for("charts.index"))

        symbol = request.form.get("symbol", "")
        timeframe = request.form.get("timeframe", "")

        filename = secure_filename(file.filename)
        object_name = _upload_to_storage(file, filename)

        job = ExtractionJob(
            organization_id=org.id,
            filename=filename,
            object_name=object_name,
            symbol=symbol,
            timeframe=timeframe,
            status="processing",
        )
        _set_audit_fields(job)
        db.session.add(job)
        db.session.commit()

        if not EXTRACTOR_AVAILABLE:
            job.status = "failed"
            job.error_message = "Extraction dependencies not available"
            _set_audit_updated(job)
            db.session.commit()
            flash("Extraction unavailable: missing dependencies", "error")
            return redirect(url_for("charts.index"))

        try:
            result = _extract_from_storage(object_name)

            job.status = "completed" if result.candles else "failed"
            job.candle_count = len(result.candles)
            job.quality_score = result.quality_score
            if symbol:
                job.symbol = symbol
            if timeframe:
                job.timeframe = timeframe
            _set_audit_updated(job)

            for i, cd in enumerate(result.candles):
                candle = Candle(
                    job_id=job.id,
                    index=i,
                    direction=cd["direction"],
                    open=cd["open"],
                    high=cd["high"],
                    low=cd["low"],
                    close=cd["close"],
                    volume=cd.get("volume"),
                    body=cd["body"],
                    upper_wick=cd["upper_wick"],
                    lower_wick=cd["lower_wick"],
                    confidence=cd["confidence"],
                )
                _set_audit_fields(candle)
                db.session.add(candle)

            db.session.commit()
            flash(
                f"Extracted {len(result.candles)} candles (quality: {result.quality_score:.0%})",
                "success",
            )
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            _set_audit_updated(job)
            db.session.commit()
            flash(f"Extraction failed: {e}", "error")

        return redirect(url_for("charts.index"))

    jobs = ExtractionJob.query.filter_by(organization_id=org.id).order_by(
        ExtractionJob.created_at.desc()
    ).all()
    return render_template("charts.html", jobs=jobs, storage_ok=storage_available())


@charts_bp.route("/uploads/<path:object_name>")
def uploaded_file(object_name):
    storage = get_storage()

    if current_app.config.get("STORAGE_BACKEND") == "local":
        from app.utils.storage import LocalStorage
        if isinstance(storage, LocalStorage):
            fp = storage._resolve(object_name)
            try:
                return send_file(fp, mimetype=mimetypes.guess_type(fp)[0] or "image/png")
            except FileNotFoundError:
                current_app.logger.warning(f"Local file not found at {fp}")
                fp = os.path.normpath(os.path.join(
                    current_app.config.get("UPLOAD_FOLDER", "").rstrip("/"),
                    object_name.lstrip("/")
                ))
                try:
                    return send_file(fp, mimetype=mimetypes.guess_type(fp)[0] or "image/png")
                except FileNotFoundError:
                    pass

    url = storage.get_url(object_name, expires=3600)
    if url and url.startswith("http"):
        return redirect(url)

    data = storage.download_bytes(object_name)
    mime = mimetypes.guess_type(object_name)[0] or "image/png"
    return send_file(io.BytesIO(data), mimetype=mime)


@charts_bp.route("/job/<int:job_id>")
@login_required
@org_required
def job_detail(job_id):
    org = g.current_org
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first_or_404()
    candles_list = job.candles.order_by(Candle.index).all()
    return render_template(
        "job_detail.html",
        job=job,
        candles=candles_list,
        storage_ok=storage_available(),
    )


@charts_bp.route("/job/<int:job_id>/delete", methods=["POST"])
@login_required
@org_required
def delete_job(job_id):
    org = g.current_org
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first_or_404()

    if storage_available() and job.object_name:
        get_storage().delete(job.object_name)

    Candle.query.filter_by(job_id=job.id).delete()
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted", "success")
    return redirect(url_for("charts.index"))


@charts_bp.route("/job/<int:job_id>/reprocess", methods=["POST"])
@login_required
@org_required
def reprocess_job(job_id):
    org = g.current_org
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first_or_404()
    if not job.object_name:
        flash("No uploaded image to reprocess", "error")
        return redirect(url_for("charts.job_detail", job_id=job_id))

    if not EXTRACTOR_AVAILABLE:
        flash("Extraction unavailable: missing dependencies", "error")
        return redirect(url_for("charts.job_detail", job_id=job_id))

    try:
        Candle.query.filter_by(job_id=job.id).delete()
        db.session.flush()

        result = _extract_from_storage(job.object_name)

        job.status = "completed" if result.candles else "failed"
        job.candle_count = len(result.candles)
        job.quality_score = result.quality_score
        _set_audit_updated(job)

        for i, cd in enumerate(result.candles):
            candle = Candle(
                job_id=job.id,
                index=i,
                direction=cd["direction"],
                open=cd["open"],
                high=cd["high"],
                low=cd["low"],
                close=cd["close"],
                volume=cd.get("volume"),
                body=cd["body"],
                upper_wick=cd["upper_wick"],
                lower_wick=cd["lower_wick"],
                confidence=cd["confidence"],
            )
            _set_audit_fields(candle)
            db.session.add(candle)

        db.session.commit()
        flash(
            f"Reprocessed: {len(result.candles)} candles (quality: {result.quality_score:.0%})",
            "success",
        )
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        _set_audit_updated(job)
        db.session.commit()
        flash(f"Reprocess failed: {e}", "error")

    return redirect(url_for("charts.job_detail", job_id=job_id))


@charts_bp.route("/job/<int:job_id>/export")
@login_required
@org_required
def export_job(job_id):
    org = g.current_org
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first_or_404()
    candles_list = job.candles.order_by(Candle.index).all()
    data = {
        "metadata": {
            "filename": job.filename,
            "symbol": job.symbol,
            "timeframe": job.timeframe,
            "quality_score": job.quality_score,
            "candle_count": job.candle_count,
        },
        "candles": [
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
            for c in candles_list
        ],
    }
    return current_app.response_class(
        json.dumps(data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=job_{job.id}.json"},
    )
