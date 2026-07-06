import os
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from werkzeug.utils import secure_filename
from app import db
from app.models import ExtractionJob

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

        job = ExtractionJob(filename=filename, status="pending")
        db.session.add(job)
        db.session.commit()

        flash("Chart uploaded successfully", "success")
        return redirect(url_for("charts.index"))

    jobs = ExtractionJob.query.order_by(ExtractionJob.created_at.desc()).all()
    return render_template("charts.html", jobs=jobs)


@charts_bp.route("/job/<int:job_id>")
def job_detail(job_id):
    job = ExtractionJob.query.get_or_404(job_id)
    return render_template("job_detail.html", job=job)


@charts_bp.route("/job/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = ExtractionJob.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted", "success")
    return redirect(url_for("charts.index"))
