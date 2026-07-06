import os
import json
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app, send_from_directory
)
from werkzeug.utils import secure_filename
from app import db
from app.models import ExtractionJob, Candle
from app.utils.extractor import ChartExtractor

charts_bp = Blueprint("charts", __name__, url_prefix="/charts")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@charts_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("chart_image")
        if not file or not file.filename:
            flash("No file selected", "error")
            return redirect(url_for("charts.index"))

        if not allowed_file(file.filename):
            flash("File type not allowed", "error")
            return redirect(url_for("charts.index"))

        filename = secure_filename(file.filename)
        upload_path = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_path, exist_ok=True)
        filepath = os.path.join(upload_path, filename)
        file.save(filepath)

        symbol = request.form.get("symbol", "")
        timeframe = request.form.get("timeframe", "")

        job = ExtractionJob(
            filename=filename,
            symbol=symbol,
            timeframe=timeframe,
            status="processing",
        )
        db.session.add(job)
        db.session.commit()

        try:
            extractor = ChartExtractor()
            result = extractor.extract(filepath)

            job.status = "completed" if result.candles else "failed"
            job.candle_count = len(result.candles)
            job.quality_score = result.quality_score
            if symbol:
                job.symbol = symbol
            if timeframe:
                job.timeframe = timeframe

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
                db.session.add(candle)

            db.session.commit()
            flash(
                f"Extracted {len(result.candles)} candles (quality: {result.quality_score:.0%})",
                "success",
            )
        except Exception as e:
            job.status = "failed"
            db.session.commit()
            flash(f"Extraction failed: {e}", "error")

        return redirect(url_for("charts.index"))

    jobs = ExtractionJob.query.order_by(ExtractionJob.created_at.desc()).all()
    return render_template("charts.html", jobs=jobs)


@charts_bp.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@charts_bp.route("/job/<int:job_id>")
def job_detail(job_id):
    job = ExtractionJob.query.get_or_404(job_id)
    candles = job.candles.order_by(Candle.index).all()
    return render_template("job_detail.html", job=job, candles=candles)


@charts_bp.route("/job/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = ExtractionJob.query.get_or_404(job_id)
    Candle.query.filter_by(job_id=job.id).delete()
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted", "success")
    return redirect(url_for("charts.index"))


@charts_bp.route("/job/<int:job_id>/export")
def export_job(job_id):
    job = ExtractionJob.query.get_or_404(job_id)
    candles = job.candles.order_by(Candle.index).all()
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
            for c in candles
        ],
    }
    return current_app.response_class(
        json.dumps(data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=job_{job.id}.json"},
    )
