import statistics
from flask import Blueprint, render_template, request, jsonify, g
from flask_login import login_required, current_user
from app import db
from app.models import Rule
from app.utils.auth import org_required

predict_bp = Blueprint("predict", __name__, url_prefix="/predict")


@predict_bp.route("/api/rules", methods=["GET"])
@login_required
@org_required
def list_rules():
    rules = Rule.query.filter_by(organization_id=g.current_org.id).order_by(Rule.id).all()
    return jsonify([{
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "conditions": r.conditions,
        "is_active": r.is_active,
    } for r in rules])


@predict_bp.route("/api/rules", methods=["POST"])
@login_required
@org_required
def create_rule():
    data = request.get_json(force=True)
    rule = Rule(
        organization_id=g.current_org.id,
        name=data.get("name", "Unnamed"),
        description=data.get("description", ""),
        conditions=data.get("conditions", []),
        is_active=data.get("is_active", True),
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify({"id": rule.id}), 201


@predict_bp.route("/api/rules/<int:rule_id>", methods=["PUT"])
@login_required
@org_required
def update_rule(rule_id):
    rule = Rule.query.filter_by(id=rule_id, organization_id=g.current_org.id).first_or_404()
    data = request.get_json(force=True)
    rule.name = data.get("name", rule.name)
    rule.description = data.get("description", rule.description)
    rule.conditions = data.get("conditions", rule.conditions)
    rule.is_active = data.get("is_active", rule.is_active)
    rule.updated_by_id = current_user.id
    db.session.commit()
    return jsonify({"ok": True})


@predict_bp.route("/api/rules/<int:rule_id>", methods=["DELETE"])
@login_required
@org_required
def delete_rule(rule_id):
    rule = Rule.query.filter_by(id=rule_id, organization_id=g.current_org.id).first_or_404()
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"ok": True})


@predict_bp.route("/api/project", methods=["POST"])
@login_required
@org_required
def project():
    data = request.get_json(force=True)
    candle_data = data.get("candles", [])
    rule_ids = data.get("rule_ids", [])

    if not candle_data or len(candle_data) < 3:
        return jsonify({"error": "Need at least 3 candles"}), 400

    rules = Rule.query.filter(
        Rule.id.in_(rule_ids),
        Rule.organization_id == g.current_org.id,
        Rule.is_active == True,
    ).all()

    if not rules:
        return jsonify({"error": "No active rules selected"}), 400

    last = candle_data[-1]
    second_last = candle_data[-2]
    third_last = candle_data[-3] if len(candle_data) >= 3 else None

    predictions = []
    for rule in rules:
        result = evaluate_rule(rule.conditions, candle_data, last, second_last, third_last)
        if result is not None:
            predictions.append(result)

    if not predictions:
        return jsonify({"projection": None, "reason": "No rule triggered"})

    bullish_votes = sum(1 for p in predictions if p["direction"] == "bullish")
    bearish_votes = sum(1 for p in predictions if p["direction"] == "bearish")

    avg_body = statistics.mean([abs(c["close"] - c["open"]) for c in candle_data[-10:]])
    avg_range = statistics.mean([c["high"] - c["low"] for c in candle_data[-10:]])
    avg_change = statistics.mean([c["close"] - c["open"] for c in candle_data[-10:]])

    if bullish_votes > bearish_votes:
        direction = "bullish"
    elif bearish_votes > bullish_votes:
        direction = "bearish"
    else:
        direction = "bullish" if avg_change >= 0 else "bearish"

    proj_open = last["close"]
    body = avg_body * 0.8
    wick = avg_range * 0.3
    if direction == "bullish":
        proj_close = proj_open + body
        proj_high = proj_close + wick
        proj_low = proj_open - wick * 0.5
    else:
        proj_close = proj_open - body
        proj_high = proj_open + wick * 0.5
        proj_low = proj_close - wick

    return jsonify({
        "projection": {
            "time": (last.get("time", 0) or 0) + 86400,
            "open": round(proj_open, 6),
            "high": round(proj_high, 6),
            "low": round(proj_low, 6),
            "close": round(proj_close, 6),
            "direction": direction,
            "confidence": round(max(bullish_votes, bearish_votes) / len(predictions), 2),
        },
        "votes": {"bullish": bullish_votes, "bearish": bearish_votes, "total": len(predictions)},
    })


def evaluate_rule(conditions, candles, last, second_last, third_last):
    triggered = []
    for cond in conditions:
        t = cond.get("type")
        val = cond.get("value")
        if t == "consecutive_bullish":
            n = val if val else 2
            if all(candles[-i - 1]["close"] >= candles[-i - 1]["open"] for i in range(min(n, len(candles)))):
                triggered.append("bearish" if n >= 2 else None)
        elif t == "consecutive_bearish":
            n = val if val else 2
            if all(candles[-i - 1]["close"] < candles[-i - 1]["open"] for i in range(min(n, len(candles)))):
                triggered.append("bullish" if n >= 2 else None)
        elif t == "long_upper_wick":
            ratio = val if val else 0.5
            upper = last["high"] - max(last["open"], last["close"])
            rng = last["high"] - last["low"]
            if rng > 0 and upper / rng >= ratio:
                triggered.append("bearish")
        elif t == "long_lower_wick":
            ratio = val if val else 0.5
            lower = min(last["open"], last["close"]) - last["low"]
            rng = last["high"] - last["low"]
            if rng > 0 and lower / rng >= ratio:
                triggered.append("bullish")
        elif t == "volume_spike":
            mult = val if val else 2.0
            vol = last.get("volume", 0)
            if vol and len(candles) >= 5:
                avg_vol = statistics.mean([c.get("volume", 0) for c in candles[-6:-1]])
                if avg_vol > 0 and vol / avg_vol >= mult:
                    triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "marubozu":
            body = abs(last["close"] - last["open"])
            rng = last["high"] - last["low"]
            if rng > 0 and body / rng >= 0.85:
                triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "doji":
            body = abs(last["close"] - last["open"])
            rng = last["high"] - last["low"]
            if rng > 0 and body / rng <= 0.1:
                triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "engulfing":
            if third_last:
                prev_body = abs(second_last["close"] - second_last["open"])
                curr_body = abs(last["close"] - last["open"])
                if curr_body > prev_body * 1.2:
                    prev_dir = second_last["close"] >= second_last["open"]
                    curr_dir = last["close"] >= last["open"]
                    if prev_dir != curr_dir:
                        triggered.append("bullish" if curr_dir else "bearish")

    if not triggered:
        return None
    bullish = sum(1 for t in triggered if t == "bullish")
    bearish = sum(1 for t in triggered if t == "bearish")
    direction = "bullish" if bullish >= bearish else "bearish"
    return {"direction": direction, "triggered": triggered}



