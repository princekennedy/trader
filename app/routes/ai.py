from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, g
from flask_login import login_required
from werkzeug.utils import secure_filename
from app.utils.detector import detect_on_bytes
from app.utils.storage import get_storage, storage_available
from app.utils.auth import org_required
from app.routes.charts import _object_name, _upload_to_storage, allowed_file

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


@ai_bp.route("/", methods=["GET", "POST"])
@login_required
@org_required
def index():
    results_list = []
    preview_url = None

    if request.method == "POST":
        file = request.files.get("image")
        if not file or not file.filename:
            flash("No file selected", "error")
            return redirect(url_for("ai.index"))

        if not allowed_file(file.filename):
            flash("File type not allowed", "error")
            return redirect(url_for("ai.index"))

        data = file.read()
        detections = detect_on_bytes(data)
        results_list = detections

        if storage_available():
            file.seek(0)
            obj_name = _object_name(secure_filename(file.filename))
            _upload_to_storage(file, obj_name)
            preview_url = url_for("charts.uploaded_file", object_name=obj_name)

        flash(f"Detected {len(detections)} objects", "success")

    return render_template("ai.html", results=results_list, preview_url=preview_url)
