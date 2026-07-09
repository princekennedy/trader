import io
import json
import uuid
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app, send_file
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Organization, ExtractionJob, Candle, Strategy, user_organizations
from app.utils.storage import get_storage, storage_available
from app.utils.extractor import ChartExtractor

try:
    EXTRACTOR_AVAILABLE = True
except ImportError:
    EXTRACTOR_AVAILABLE = False

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "unauthorized", "message": "Missing API token"}), 401
        user = User.query.filter_by(api_token=token).first()
        if not user or not user.is_active:
            return jsonify({"error": "unauthorized", "message": "Invalid or inactive token"}), 401
        g.api_user = user

        org_id = request.headers.get("X-Org-Id")
        if org_id:
            org = user.organizations.filter_by(id=int(org_id)).first()
            if not org:
                return jsonify({"error": "forbidden", "message": "Organization not found or not a member"}), 403
            g.current_org = org
        else:
            g.current_org = user.organizations.first()
        return f(*args, **kwargs)
    return decorated


def _set_audit(record):
    if g.get("api_user"):
        record.created_by_id = g.api_user.id


def _set_audit_updated(record):
    if g.get("api_user"):
        record.updated_by_id = g.api_user.id


def _object_name(filename):
    return f"charts/{uuid.uuid4().hex}_{filename}"


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─────────────────────────────── Auth ───────────────────────────────


@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "validation", "message": "Email and password are required"}), 422
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "auth", "message": "Invalid email or password"}), 401
    token = user.generate_api_token()
    db.session.commit()
    return jsonify({
        "token": token,
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "organizations": [{"id": o.id, "name": o.name, "slug": o.slug} for o in user.organizations],
    })


@api_bp.route("/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or not email or not password:
        return jsonify({"error": "validation", "message": "Name, email, and password are required"}), 422
    if len(password) < 6:
        return jsonify({"error": "validation", "message": "Password must be at least 6 characters"}), 422
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "conflict", "message": "Email already registered"}), 409
    user = User(name=name, email=email)
    user.set_password(password)
    user.generate_api_token()
    db.session.add(user)
    db.session.commit()
    return jsonify({
        "token": user.api_token,
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }), 201


# ─────────────────────────────── Jobs ───────────────────────────────


@api_bp.route("/jobs", methods=["GET"])
@api_required
def api_list_jobs():
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    jobs = ExtractionJob.query.filter_by(organization_id=org.id).order_by(ExtractionJob.created_at.desc()).all()
    return jsonify([{
        "id": j.id,
        "filename": j.filename,
        "symbol": j.symbol,
        "timeframe": j.timeframe,
        "status": j.status,
        "candle_count": j.candle_count,
        "quality_score": j.quality_score,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    } for j in jobs])


@api_bp.route("/jobs", methods=["POST"])
@api_required
def api_create_job():
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403

    file = request.files.get("image") or request.files.get("chart_image")
    if not file or not file.filename:
        return jsonify({"error": "validation", "message": "Image file is required"}), 422
    if not _allowed_file(file.filename):
        return jsonify({"error": "validation", "message": "File type not allowed"}), 422

    symbol = request.form.get("symbol", "")
    timeframe = request.form.get("timeframe", "")

    filename = secure_filename(file.filename)
    storage = get_storage()
    obj_name = _object_name(filename)
    storage.upload_bytes(file.read(), obj_name, content_type=file.content_type or "image/png")

    job = ExtractionJob(
        organization_id=org.id, filename=filename, object_name=obj_name,
        symbol=symbol, timeframe=timeframe, status="processing",
    )
    _set_audit(job)
    db.session.add(job)
    db.session.commit()

    if not EXTRACTOR_AVAILABLE:
        job.status = "failed"
        db.session.commit()
        return jsonify({"error": "extraction", "message": "Extraction unavailable"}), 500

    try:
        Candle.query.filter_by(job_id=job.id).delete()
        db.session.flush()

        data = get_storage().download_bytes(obj_name)
        extractor = ChartExtractor()
        result = extractor.extract_from_bytes(data)

        job.status = "completed" if result.candles else "failed"
        job.candle_count = len(result.candles)
        job.quality_score = result.quality_score
        _set_audit_updated(job)

        for i, cd in enumerate(result.candles):
            candle = Candle(
                job_id=job.id, index=i, direction=cd["direction"],
                open=cd["open"], high=cd["high"], low=cd["low"], close=cd["close"],
                volume=cd.get("volume"), body=cd["body"],
                upper_wick=cd["upper_wick"], lower_wick=cd["lower_wick"],
                confidence=cd["confidence"],
            )
            _set_audit(candle)
            db.session.add(candle)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        job.status = "failed"
        db.session.commit()
        return jsonify({"error": "extraction", "message": str(e)}), 500

    return jsonify({
        "id": job.id, "filename": job.filename, "symbol": job.symbol,
        "timeframe": job.timeframe, "status": job.status,
        "candle_count": job.candle_count, "quality_score": job.quality_score,
    }), 201


@api_bp.route("/jobs/<int:job_id>", methods=["GET"])
@api_required
def api_get_job(job_id):
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first()
    if not job:
        return jsonify({"error": "not_found", "message": "Job not found"}), 404
    return jsonify({
        "id": job.id, "filename": job.filename, "symbol": job.symbol,
        "timeframe": job.timeframe, "status": job.status,
        "candle_count": job.candle_count, "quality_score": job.quality_score,
        "error_message": job.error_message, "object_name": job.object_name,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    })


@api_bp.route("/jobs/<int:job_id>", methods=["DELETE"])
@api_required
def api_delete_job(job_id):
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first()
    if not job:
        return jsonify({"error": "not_found", "message": "Job not found"}), 404
    if storage_available() and job.object_name:
        get_storage().delete(job.object_name)
    Candle.query.filter_by(job_id=job.id).delete()
    db.session.delete(job)
    db.session.commit()
    return jsonify({"message": "Job deleted"}), 200


@api_bp.route("/jobs/<int:job_id>/reprocess", methods=["POST"])
@api_required
def api_reprocess_job(job_id):
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first()
    if not job:
        return jsonify({"error": "not_found", "message": "Job not found"}), 404
    if not job.object_name:
        return jsonify({"error": "validation", "message": "No uploaded image to reprocess"}), 422
    if not EXTRACTOR_AVAILABLE:
        return jsonify({"error": "extraction", "message": "Extraction unavailable"}), 500

    try:
        Candle.query.filter_by(job_id=job.id).delete()
        db.session.flush()
        data = get_storage().download_bytes(job.object_name)
        extractor = ChartExtractor()
        result = extractor.extract_from_bytes(data)

        job.status = "completed" if result.candles else "failed"
        job.candle_count = len(result.candles)
        job.quality_score = result.quality_score
        _set_audit_updated(job)

        for i, cd in enumerate(result.candles):
            candle = Candle(
                job_id=job.id, index=i, direction=cd["direction"],
                open=cd["open"], high=cd["high"], low=cd["low"], close=cd["close"],
                volume=cd.get("volume"), body=cd["body"],
                upper_wick=cd["upper_wick"], lower_wick=cd["lower_wick"],
                confidence=cd["confidence"],
            )
            _set_audit(candle)
            db.session.add(candle)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        job.status = "failed"
        db.session.commit()
        return jsonify({"error": "extraction", "message": str(e)}), 500

    return jsonify({"id": job.id, "status": job.status, "candle_count": job.candle_count, "quality_score": job.quality_score})


@api_bp.route("/jobs/<int:job_id>/candles", methods=["GET"])
@api_required
def api_get_candles(job_id):
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first()
    if not job:
        return jsonify({"error": "not_found", "message": "Job not found"}), 404
    candles = Candle.query.filter_by(job_id=job.id).order_by(Candle.index).all()
    return jsonify([{
        "index": c.index, "direction": c.direction,
        "open": c.open, "high": c.high, "low": c.low, "close": c.close,
        "volume": c.volume, "body": c.body,
        "upper_wick": c.upper_wick, "lower_wick": c.lower_wick,
        "confidence": c.confidence,
    } for c in candles])


@api_bp.route("/jobs/<int:job_id>/image")
@api_required
def api_job_image(job_id):
    org = g.current_org
    if not org:
        return jsonify({"error": "forbidden", "message": "No organization selected"}), 403
    job = ExtractionJob.query.filter_by(id=job_id, organization_id=org.id).first()
    if not job or not job.object_name:
        return jsonify({"error": "not_found", "message": "Image not found"}), 404
    data = get_storage().download_bytes(job.object_name)
    import mimetypes
    mime = mimetypes.guess_type(job.object_name)[0] or "image/png"
    return send_file(io.BytesIO(data), mimetype=mime)


# ─────────────────────────────── Orgs ───────────────────────────────


@api_bp.route("/orgs", methods=["GET"])
@api_required
def api_list_orgs():
    user = g.api_user
    orgs = user.organizations.all()
    return jsonify([{
        "id": o.id, "name": o.name, "slug": o.slug,
        "description": o.description,
        "owner_id": o.owner_id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    } for o in orgs])


@api_bp.route("/orgs", methods=["POST"])
@api_required
def api_create_org():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "validation", "message": "Organization name is required"}), 422
    import re
    slug = name.lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not slug:
        return jsonify({"error": "validation", "message": "Invalid organization name"}), 422
    if Organization.query.filter_by(slug=slug).first():
        return jsonify({"error": "conflict", "message": "Organization with this name already exists"}), 409

    org = Organization(name=name, slug=slug, description=data.get("description", ""), owner_id=g.api_user.id)
    _set_audit(org)
    db.session.add(org)
    db.session.flush()

    stmt = user_organizations.insert().values(user_id=g.api_user.id, organization_id=org.id, role="admin")
    db.session.execute(stmt)
    db.session.commit()

    return jsonify({"id": org.id, "name": org.name, "slug": org.slug, "description": org.description}), 201


@api_bp.route("/orgs/<int:org_id>/switch", methods=["POST"])
@api_required
def api_switch_org(org_id):
    org = g.api_user.organizations.filter_by(id=org_id).first()
    if not org:
        return jsonify({"error": "not_found", "message": "Organization not found"}), 404
    g.current_org = org
    return jsonify({"id": org.id, "name": org.name, "slug": org.slug, "message": f"Switched to {org.name}"})


@api_bp.route("/orgs/<int:org_id>/members", methods=["GET"])
@api_required
def api_list_members(org_id):
    org = g.api_user.organizations.filter_by(id=org_id).first()
    if not org:
        return jsonify({"error": "not_found", "message": "Organization not found"}), 404
    members = db.session.query(User, user_organizations.c.role).join(
        user_organizations, User.id == user_organizations.c.user_id
    ).filter(user_organizations.c.organization_id == org.id).all()
    return jsonify([{
        "id": m[0].id, "name": m[0].name, "email": m[0].email, "role": m[1],
    } for m in members])


@api_bp.route("/orgs/<int:org_id>/members", methods=["POST"])
@api_required
def api_add_member(org_id):
    org = g.api_user.organizations.filter_by(id=org_id).first()
    if not org:
        return jsonify({"error": "not_found", "message": "Organization not found"}), 404
    if org.owner_id != g.api_user.id:
        return jsonify({"error": "forbidden", "message": "Only the owner can add members"}), 403

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    role = data.get("role", "member")
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "not_found", "message": "User not found"}), 404

    existing = db.session.execute(
        user_organizations.select().where(
            user_organizations.c.user_id == user.id,
            user_organizations.c.organization_id == org.id,
        )
    ).first()
    if existing:
        return jsonify({"error": "conflict", "message": "User is already a member"}), 409

    stmt = user_organizations.insert().values(user_id=user.id, organization_id=org.id, role=role)
    db.session.execute(stmt)
    db.session.commit()
    return jsonify({"message": f"Added {user.name} as {role}"}), 201


@api_bp.route("/orgs/<int:org_id>/members/<int:user_id>", methods=["DELETE"])
@api_required
def api_remove_member(org_id, user_id):
    org = g.api_user.organizations.filter_by(id=org_id).first()
    if not org:
        return jsonify({"error": "not_found", "message": "Organization not found"}), 404
    if org.owner_id != g.api_user.id:
        return jsonify({"error": "forbidden", "message": "Only the owner can remove members"}), 403
    if user_id == g.api_user.id:
        return jsonify({"error": "validation", "message": "You cannot remove yourself"}), 422

    stmt = user_organizations.delete().where(
        user_organizations.c.user_id == user_id,
        user_organizations.c.organization_id == org_id,
    )
    db.session.execute(stmt)
    db.session.commit()
    return jsonify({"message": "Member removed"})


# ─────────────────────────────── AI ───────────────────────────────


@api_bp.route("/ai/detect", methods=["POST"])
@api_required
def api_detect():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "validation", "message": "Image file is required"}), 422

    try:
        from app.utils.detector import detect_on_bytes
        detections = detect_on_bytes(file.read())
    except ImportError:
        return jsonify({"error": "unavailable", "message": "AI detection dependencies not available"}), 500

    return jsonify({
        "detections": [{
            "label": d["label"],
            "confidence": d["confidence"],
            "bbox": d["bbox"],
        } for d in detections],
        "count": len(detections),
    })


# ─────────────────────────────── Swagger / OpenAPI ───────────────────────────────

SWAGGER_TITLE = "TradingView Candlestick Extractor API"
SWAGGER_VERSION = "1.0.0"


@api_bp.route("/docs/openapi.json")
def api_openapi_spec():
    base_url = f"{request.scheme}://{request.host}"
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": SWAGGER_TITLE,
            "version": SWAGGER_VERSION,
            "description": "REST API for the TradingView Candlestick Extractor platform. Extract OHLCV data from chart images, manage organizations, and run AI detection.",
            "contact": {"name": "Support", "email": "support@example.com"},
        },
        "servers": [{"url": f"{base_url}/api/v1", "description": "API v1"}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API token obtained from /auth/login or /auth/register"
                },
                "OrgHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Org-Id",
                    "description": "Active organization ID (optional, uses first org if omitted)"
                }
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                    }
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    }
                },
                "Organization": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "slug": {"type": "string"},
                        "description": {"type": "string"},
                        "owner_id": {"type": "integer"},
                        "created_at": {"type": "string", "format": "date-time"},
                    }
                },
                "ExtractionJob": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "filename": {"type": "string"},
                        "symbol": {"type": "string"},
                        "timeframe": {"type": "string"},
                        "status": {"type": "string"},
                        "candle_count": {"type": "integer"},
                        "quality_score": {"type": "number"},
                        "created_at": {"type": "string", "format": "date-time"},
                    }
                },
                "Candle": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "direction": {"type": "string"},
                        "open": {"type": "number"},
                        "high": {"type": "number"},
                        "low": {"type": "number"},
                        "close": {"type": "number"},
                        "volume": {"type": "number", "nullable": True},
                        "body": {"type": "number"},
                        "upper_wick": {"type": "number"},
                        "lower_wick": {"type": "number"},
                        "confidence": {"type": "number"},
                    }
                },
                "Detection": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "confidence": {"type": "number"},
                        "bbox": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                        }
                    }
                },
                "LoginRequest": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string", "format": "password"},
                    }
                },
                "RegisterRequest": {
                    "type": "object",
                    "required": ["name", "email", "password"],
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string", "format": "password"},
                    }
                },
                "CreateOrgRequest": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    }
                },
            }
        },
        "security": [{"ApiKeyAuth": []}],
        "paths": {
            "/auth/login": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Login and get API token",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoginRequest"}}}
                    },
                    "responses": {
                        "200": {
                            "description": "Login successful",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "token": {"type": "string"},
                                        "user": {"$ref": "#/components/schemas/User"},
                                        "organizations": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Organization"}
                                        }
                                    }
                                }
                            }}
                        },
                        "401": {"description": "Invalid credentials"},
                    }
                }
            },
            "/auth/register": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Register a new account",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RegisterRequest"}}}
                    },
                    "responses": {
                        "201": {"description": "Account created"},
                        "409": {"description": "Email already registered"},
                    }
                }
            },
            "/jobs": {
                "get": {
                    "tags": ["Jobs"],
                    "summary": "List extraction jobs for the active organization",
                    "responses": {
                        "200": {
                            "description": "List of jobs",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/ExtractionJob"}
                                }
                            }}
                        }
                    }
                },
                "post": {
                    "tags": ["Jobs"],
                    "summary": "Upload a chart image and extract candle data",
                    "requestBody": {
                        "required": True,
                        "content": {"multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["image"],
                                "properties": {
                                    "image": {"type": "string", "format": "binary"},
                                    "symbol": {"type": "string"},
                                    "timeframe": {"type": "string"},
                                }
                            }
                        }}
                    },
                    "responses": {
                        "201": {"description": "Job created and processed"},
                        "422": {"description": "Validation error"},
                    }
                }
            },
            "/jobs/{job_id}": {
                "get": {
                    "tags": ["Jobs"],
                    "summary": "Get job details",
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {"description": "Job details"},
                        "404": {"description": "Job not found"},
                    }
                },
                "delete": {
                    "tags": ["Jobs"],
                    "summary": "Delete a job and its candles",
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {"description": "Job deleted"},
                        "404": {"description": "Job not found"},
                    }
                }
            },
            "/jobs/{job_id}/reprocess": {
                "post": {
                    "tags": ["Jobs"],
                    "summary": "Re-extract candle data from the original image",
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {"description": "Reprocessed successfully"},
                        "404": {"description": "Job not found"},
                    }
                }
            },
            "/jobs/{job_id}/candles": {
                "get": {
                    "tags": ["Jobs"],
                    "summary": "Get extracted candle data for a job",
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {
                            "description": "Candle list",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Candle"}
                                }
                            }}
                        },
                        "404": {"description": "Job not found"},
                    }
                }
            },
            "/jobs/{job_id}/image": {
                "get": {
                    "tags": ["Jobs"],
                    "summary": "Download the original chart image",
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {"description": "Image binary"},
                        "404": {"description": "Image not found"},
                    }
                }
            },
            "/orgs": {
                "get": {
                    "tags": ["Organizations"],
                    "summary": "List organizations the authenticated user belongs to",
                    "responses": {
                        "200": {
                            "description": "Organization list",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Organization"}
                                }
                            }}
                        }
                    }
                },
                "post": {
                    "tags": ["Organizations"],
                    "summary": "Create a new organization",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateOrgRequest"}}}
                    },
                    "responses": {
                        "201": {"description": "Organization created"},
                        "409": {"description": "Name conflict"},
                    }
                }
            },
            "/orgs/{org_id}/switch": {
                "post": {
                    "tags": ["Organizations"],
                    "summary": "Switch the active organization for subsequent requests",
                    "parameters": [{"name": "org_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {"description": "Switched successfully"},
                        "404": {"description": "Organization not found"},
                    }
                }
            },
            "/orgs/{org_id}/members": {
                "get": {
                    "tags": ["Organizations"],
                    "summary": "List organization members",
                    "parameters": [{"name": "org_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {
                        "200": {
                            "description": "Member list",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "email": {"type": "string"},
                                            "role": {"type": "string"},
                                        }
                                    }
                                }
                            }}
                        },
                        "404": {"description": "Organization not found"},
                    }
                },
                "post": {
                    "tags": ["Organizations"],
                    "summary": "Add a member to the organization (owner only)",
                    "parameters": [{"name": "org_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["email"],
                                "properties": {
                                    "email": {"type": "string", "format": "email"},
                                    "role": {"type": "string"},
                                }
                            }
                        }}
                    },
                    "responses": {
                        "201": {"description": "Member added"},
                        "403": {"description": "Only owner can add members"},
                    }
                }
            },
            "/orgs/{org_id}/members/{user_id}": {
                "delete": {
                    "tags": ["Organizations"],
                    "summary": "Remove a member from the organization (owner only)",
                    "parameters": [
                        {"name": "org_id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}},
                    ],
                    "responses": {
                        "200": {"description": "Member removed"},
                        "403": {"description": "Only owner can remove members"},
                    }
                }
            },
            "/ai/detect": {
                "post": {
                    "tags": ["AI"],
                    "summary": "Run YOLO object detection on a chart image",
                    "requestBody": {
                        "required": True,
                        "content": {"multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["image"],
                                "properties": {
                                    "image": {"type": "string", "format": "binary"},
                                }
                            }
                        }}
                    },
                    "responses": {
                        "200": {
                            "description": "Detection results",
                            "content": {"application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "count": {"type": "integer"},
                                        "detections": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Detection"}
                                        }
                                    }
                                }
                            }}
                        }
                    }
                }
            }
        }
    }
    return jsonify(spec)


@api_bp.route("/docs")
def api_swagger_ui():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{SWAGGER_TITLE}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.3/swagger-ui.css">
  <style>
    body {{ margin: 0; background: #f8fafc; }}
    .swagger-ui .topbar {{ display: none; }}
    .swagger-ui .info {{ margin: 20px 0; }}
    .swagger-ui .scheme-container {{ background: #fff; box-shadow: none; border-radius: 8px; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.3/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{
      url: '{request.url_root.rstrip("/")}/api/v1/docs/openapi.json',
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset,
      ],
      layout: 'BaseLayout',
    }});
  </script>
</body>
</html>"""
