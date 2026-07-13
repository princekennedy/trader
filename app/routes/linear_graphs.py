import json
from flask import Blueprint, request, jsonify, g, current_app
from flask_login import login_required, current_user
from app import db
from app.models import LinearGraph, AIProvider, AIKey
from app.utils.auth import org_required
from app.routes.rules import _call_openai_compat, _call_gemini

linear_graphs_bp = Blueprint("linear_graphs", __name__, url_prefix="/api/linear-graphs")

LG_GENERATE_PROMPT = """You are a trading indicator generator. Given a user's description of a technical indicator or overlay they want to see on a candlestick chart, generate a structured linear graph config in the following JSON format:

{"name":"Short Name","description":"Brief explanation","series":[{"source":"...","label":"...","color":"..."}, ...]}

The `name` field must be short (2-5 words). The `description` is a one-sentence explanation. The `series` array defines one or more line plots.

Supported source values (pick from these ONLY):
- "open" — open price line
- "high" — high price line
- "low" — low price line
- "close" — close price line
- "volume" — volume
- "body" — candle body size (abs(close-open))
- "upper_wick" — upper wick length
- "lower_wick" — lower wick length
- "range" — high-low range
- "body_ratio" — body as percentage of range (0-100)
- "upper_wick_ratio" — upper wick as percentage of range
- "lower_wick_ratio" — lower wick as percentage of range
- "hl2" — (high+low)/2
- "hlc3" — (high+low+close)/3
- "ohlc4" — (open+high+low+close)/4

Choose appropriate colors (hex) for each series. Use distinct colors for multiple series.

Respond with ONLY valid JSON, no explanation."""

LG_ANALYZE_PROMPT = """You are a professional trading analyst. Given the data from a custom linear graph indicator plotted over recent OHLCV data, analyze what the indicator is showing.

Linear Graph: {graph_name}
Description: {graph_description}
Series: {series_info}

Here is the candle data with computed indicator values (most recent last):
{data_rows}

Analyze what the indicator lines reveal about the market. Look at trends in the indicator values, crossovers, divergences with price, extreme readings, and any actionable signals. Be specific and reference actual values. 2-4 paragraphs."""


@linear_graphs_bp.route("", methods=["GET"])
@login_required
@org_required
def list_graphs():
    graphs = LinearGraph.query.filter_by(organization_id=g.current_org.id).order_by(LinearGraph.updated_at.desc()).all()
    return jsonify([{
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "config": g.config if isinstance(g.config, dict) else json.loads(g.config) if isinstance(g.config, str) else {},
        "is_active": g.is_active,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    } for g in graphs])


@linear_graphs_bp.route("", methods=["POST"])
@login_required
@org_required
def create_graph():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    config = data.get("config", {"series": []})
    if not isinstance(config, dict):
        return jsonify({"error": "config must be a JSON object with a 'series' array"}), 400
    graph = LinearGraph(
        organization_id=g.current_org.id,
        name=name,
        description=data.get("description", "").strip(),
        config=config,
        is_active=data.get("is_active", True),
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.session.add(graph)
    db.session.commit()
    return jsonify({"id": graph.id, "name": graph.name}), 201


@linear_graphs_bp.route("/<int:graph_id>", methods=["PUT"])
@login_required
@org_required
def update_graph(graph_id):
    graph = LinearGraph.query.filter_by(id=graph_id, organization_id=g.current_org.id).first()
    if not graph:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True)
    if "name" in data:
        name = data["name"].strip()
        if not name:
            return jsonify({"error": "Name cannot be empty"}), 400
        graph.name = name
    if "description" in data:
        graph.description = data["description"].strip()
    if "config" in data:
        config = data["config"]
        if not isinstance(config, dict):
            return jsonify({"error": "config must be a JSON object"}), 400
        graph.config = config
    if "is_active" in data:
        graph.is_active = bool(data["is_active"])
    graph.updated_by_id = current_user.id
    db.session.commit()
    return jsonify({"id": graph.id, "name": graph.name})


@linear_graphs_bp.route("/<int:graph_id>", methods=["DELETE"])
@login_required
@org_required
def delete_graph(graph_id):
    graph = LinearGraph.query.filter_by(id=graph_id, organization_id=g.current_org.id).first()
    if not graph:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(graph)
    db.session.commit()
    return jsonify({"ok": True})


@linear_graphs_bp.route("/generate", methods=["POST"])
@login_required
@org_required
def generate_graph():
    data = request.get_json(force=True)
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    provider = None
    user_keys = AIKey.query.filter_by(
        user_id=current_user.id, organization_id=g.current_org.id, is_active=True
    ).all()
    for uk in user_keys:
        p = AIProvider.query.get(uk.provider_id)
        if p and p.is_active:
            provider = p
            break

    if not provider:
        return jsonify({"error": "No AI provider configured. Add an API key in Rules page first."}), 400

    ai_key = AIKey.query.filter_by(
        user_id=current_user.id, organization_id=g.current_org.id,
        provider_id=provider.id, is_active=True
    ).first()

    try:
        user_prompt = f"Generate a linear graph for: {prompt}"
        if provider.slug == "gemini":
            result = _call_gemini(provider, data.get("model_slug", ""), ai_key.api_key,
                                  LG_GENERATE_PROMPT, user_prompt, json_output=True)
        else:
            result = _call_openai_compat(provider, data.get("model_slug", ""), ai_key.api_key,
                                         LG_GENERATE_PROMPT, user_prompt,
                                         response_format={"type": "json_object"})
        generated = json.loads(result) if isinstance(result, str) else result
        if "series" not in generated:
            generated["series"] = []
        return jsonify(generated)
    except Exception as e:
        current_app.logger.error("LG generate error: %s", e)
        return jsonify({"error": str(e)}), 500


@linear_graphs_bp.route("/<int:graph_id>/analyze", methods=["POST"])
@login_required
@org_required
def analyze_graph(graph_id):
    graph = LinearGraph.query.filter_by(id=graph_id, organization_id=g.current_org.id).first()
    if not graph:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(force=True)
    candle_data = data.get("candles", [])
    if not candle_data or len(candle_data) < 3:
        return jsonify({"error": "Need at least 3 candles"}), 400

    question = data.get("question", "").strip()
    provider_slug = data.get("provider_slug", "")
    model_slug = data.get("model_slug", "")

    provider = None
    if provider_slug:
        provider = AIProvider.query.filter_by(slug=provider_slug, is_active=True).first()
    if not provider:
        user_keys = AIKey.query.filter_by(
            user_id=current_user.id, organization_id=g.current_org.id, is_active=True
        ).all()
        for uk in user_keys:
            p = AIProvider.query.get(uk.provider_id)
            if p and p.is_active:
                provider = p
                break

    if not provider:
        return jsonify({"error": "No AI provider configured. Add an API key in Rules page first."}), 400

    ai_key = AIKey.query.filter_by(
        user_id=current_user.id, organization_id=g.current_org.id,
        provider_id=provider.id, is_active=True
    ).first()

    config = graph.config if isinstance(graph.config, dict) else json.loads(graph.config) if isinstance(graph.config, str) else {"series": []}
    series_info = "; ".join([f"{s.get('source','?')} (label: {s.get('label','?')}, color: {s.get('color','?')})" for s in config.get("series", [])])

    last_n = candle_data[-50:]
    data_rows = []
    for i, c in enumerate(last_n):
        vals = []
        for s in config.get("series", []):
            sv = _compute_source(c, s["source"])
            vals.append(f"{s['source']}={sv:.4f}")
        label = f"[{c.get('time', i+1)}] O:{c['open']:.4f} H:{c['high']:.4f} L:{c['low']:.4f} C:{c['close']:.4f} | {' '.join(vals)}"
        data_rows.append(label)

    user_prompt = LG_ANALYZE_PROMPT.format(
        graph_name=graph.name,
        graph_description=graph.description or "No description",
        series_info=series_info,
        data_rows="\n".join(data_rows),
    )
    if question:
        user_prompt += f"\n\nAdditional user question: {question}"

    try:
        if provider.slug == "gemini":
            answer = _call_gemini(provider, model_slug, ai_key.api_key,
                                  "You are a professional trading analyst.", user_prompt)
        else:
            answer = _call_openai_compat(provider, model_slug, ai_key.api_key,
                                         "You are a professional trading analyst.", user_prompt)
        return jsonify({"answer": answer.strip()})
    except Exception as e:
        current_app.logger.error("LG analyze error: %s", e)
        return jsonify({"error": str(e)}), 500


def _compute_source(candle, source):
    o = float(candle.get("open", 0))
    h = float(candle.get("high", 0))
    l = float(candle.get("low", 0))
    cl = float(candle.get("close", 0))
    v = float(candle.get("volume", 0))
    body = candle.get("body")
    if body is None:
        body = abs(cl - o)
    upper = candle.get("upper_wick")
    if upper is None:
        upper = h - max(o, cl)
    lower = candle.get("lower_wick")
    if lower is None:
        lower = min(o, cl) - l
    rng = h - l
    sources = {
        "open": o, "high": h, "low": l, "close": cl, "volume": v,
        "body": body, "upper_wick": upper, "lower_wick": lower,
        "range": rng,
        "body_ratio": (body / rng * 100) if rng > 0 else 0,
        "upper_wick_ratio": (upper / rng * 100) if rng > 0 else 0,
        "lower_wick_ratio": (lower / rng * 100) if rng > 0 else 0,
        "hl2": (h + l) / 2,
        "hlc3": (h + l + cl) / 3,
        "ohlc4": (o + h + l + cl) / 4,
    }
    return sources.get(source, 0)
