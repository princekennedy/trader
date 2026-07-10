import json
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, g, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import AIProvider, AIProviderModel, AIKey, Rule
from app.utils.detector import detect_on_bytes
from app.utils.storage import storage_available
from app.utils.auth import org_required
from app.routes.charts import _object_name, _upload_to_storage, allowed_file

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")

SYSTEM_PROMPT = """You are a trading rule generator. Given a user's description of a trading pattern or rule, generate a structured rule in the following JSON format:

{"version":2,"conditions":[...],"action":"bullish"|"bearish"}

Condition types:
- {"type":"pattern","params":{"consecutive":2,"direction":"bearish"}} — N consecutive candles of a direction
- {"type":"wick_comparison","params":{"candle_a":-2,"candle_b":-1,"part":"upper"|"lower","comparison":"gt"|"lt"}} — compare wick parts between two candles (candle_a and candle_b are 0-indexed relative to current, -1 = last candle)
- {"type":"body_comparison","params":{"candle_a":-2,"candle_b":-1,"comparison":"gt"|"lt"}} — compare body sizes
- {"type":"range","params":{"candle":-1,"part":"body"|"wick_upper"|"wick_lower"|"full","min_pips":0.0,"max_pips":100.0}} — candle part in pip range
- {"type":"close_position","params":{"candle":-1,"position":"above"|"below","reference":"open"|"ema_9"|"ema_21"|"ema_50"}} — close relative to reference
- {"type":"volume","params":{"candle":-1,"comparison":"gt"|"lt","multiplier":1.5}} — volume compared to average
- {"type":"timeframe","params":{"value":"1m"|"5m"|"15m"|"1h"|"4h"|"1d"}} — required timeframe
- {"type":"and"} / {"type":"or"} — logical grouping (children follow)

Respond with ONLY valid JSON, no explanation."""


@ai_bp.route("/", methods=["GET", "POST"])
@login_required
@org_required
def index():
    results_list = []
    preview_url = None
    org = g.organization
    providers = AIProvider.query.filter_by(is_active=True).all()
    user_keys = AIKey.query.filter_by(user_id=current_user.id, organization_id=org.id, is_active=True).all()
    configured_provider_ids = {k.provider_id for k in user_keys}

    if request.method == "POST":
        file = request.files.get("image")
        if not file or not file.filename:
            flash("No file selected", "error")
            return redirect(url_for("ai.index"))
        if not allowed_file(file.filename):
            flash("File type not allowed", "error")
            return redirect(url_for("ai.index"))
        data = file.read()
        try:
            detections = detect_on_bytes(data)
        except Exception as e:
            current_app.logger.error("Detection error: %s", e)
            flash("AI model error: the model does not support this image format. Try a different image.", "error")
            return redirect(url_for("ai.index"))
        results_list = detections
        if storage_available():
            file.seek(0)
            obj_name = _object_name(secure_filename(file.filename))
            _upload_to_storage(file, obj_name)
            preview_url = url_for("charts.uploaded_file", object_name=obj_name)
        flash(f"Detected {len(detections)} objects", "success")

    first_config = None
    for p in providers:
        if p.id in configured_provider_ids:
            first_config = {"slug": p.slug, "default_model": p.default_model or ""}
            break

    return render_template("ai.html", results=results_list, preview_url=preview_url, providers=providers, configured_provider_ids=configured_provider_ids, first_config=first_config)


@ai_bp.route("/config/models/<int:provider_id>")
@login_required
@org_required
def provider_models(provider_id):
    models = AIProviderModel.query.filter_by(provider_id=provider_id, is_active=True).all()
    return jsonify([{"id": m.id, "name": m.name, "slug": m.slug} for m in models])


@ai_bp.route("/config/save-key", methods=["POST"])
@login_required
@org_required
def save_key():
    org = g.organization
    data = request.get_json()
    provider_id = data.get("provider_id")
    api_key = data.get("api_key")
    if not provider_id or not api_key:
        return jsonify({"error": "Missing provider_id or api_key"}), 400
    provider = AIProvider.query.get(provider_id)
    if not provider:
        return jsonify({"error": "Provider not found"}), 404
    existing = AIKey.query.filter_by(user_id=current_user.id, organization_id=org.id, provider_id=provider_id, is_active=True).first()
    if existing:
        existing.api_key = api_key
    else:
        db.session.add(AIKey(user_id=current_user.id, organization_id=org.id, provider_id=provider_id, api_key=api_key, created_by_id=current_user.id, updated_by_id=current_user.id))
    db.session.commit()
    return jsonify({"ok": True})


@ai_bp.route("/generate-rule", methods=["POST"])
@login_required
@org_required
def generate_rule():
    org = g.organization
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    provider_slug = data.get("provider_slug", "")
    model_slug = data.get("model_slug", "")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    provider = AIProvider.query.filter_by(slug=provider_slug, is_active=True).first()
    if not provider:
        return jsonify({"error": "AI provider not found"}), 404

    ai_key = AIKey.query.filter_by(user_id=current_user.id, organization_id=org.id, provider_id=provider.id, is_active=True).first()
    if not ai_key:
        return jsonify({"error": "API key not configured for this provider"}), 400

    try:
        if provider.slug == "gemini":
            rule_json = _call_gemini(provider, model_slug, ai_key.api_key, prompt)
        else:
            rule_json = _call_openai_compat(provider, model_slug, ai_key.api_key, prompt)

        parsed = json.loads(rule_json)
        return jsonify({"rule": parsed})
    except json.JSONDecodeError as e:
        return jsonify({"error": "AI returned invalid JSON", "raw": rule_json}), 500
    except Exception as e:
        current_app.logger.error("AI rule generation error: %s", e)
        return jsonify({"error": str(e)}), 500


def _call_openai_compat(provider, model_slug, api_key, prompt):
    url = provider.base_url.rstrip("/") + provider.chat_endpoint
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_slug or provider.default_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return body["choices"][0]["message"]["content"]


def _call_gemini(provider, model_slug, api_key, prompt):
    model = model_slug or provider.default_model
    endpoint = provider.chat_endpoint.replace("{model}", model)
    url = provider.base_url.rstrip("/") + endpoint + f"?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\nUser: {prompt}"}]
        }]
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return body["candidates"][0]["content"]["parts"][0]["text"]


@ai_bp.route("/save-rule", methods=["POST"])
@login_required
@org_required
def save_rule():
    org = g.organization
    data = request.get_json()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    conditions = data.get("conditions")
    if not name or not conditions:
        return jsonify({"error": "Name and conditions are required"}), 400
    rule = Rule(
        organization_id=org.id,
        name=name,
        description=description,
        conditions=conditions,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify({"ok": True, "rule_id": rule.id})
