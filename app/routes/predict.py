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

    predictions = []
    for rule in rules:
        result = evaluate_rule(rule.conditions, candle_data)
        if result is not None:
            predictions.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                **result,
            })

    avg_body = statistics.mean([abs(c["close"] - c["open"]) for c in candle_data[-10:]])
    avg_range = statistics.mean([c["high"] - c["low"] for c in candle_data[-10:]])
    avg_change = statistics.mean([c["close"] - c["open"] for c in candle_data[-10:]])

    if predictions:
        bullish_votes = sum(1 for p in predictions if p["direction"] == "bullish")
        bearish_votes = sum(1 for p in predictions if p["direction"] == "bearish")
        fallback = False
    else:
        bullish_votes = 0
        bearish_votes = 0
        fallback = True

    if bullish_votes > bearish_votes:
        direction = "bullish"
    elif bearish_votes > bullish_votes:
        direction = "bearish"
    else:
        direction = "bullish" if avg_change >= 0 else "bearish"
        if not predictions:
            direction = "bullish" if candle_data[-1]["close"] >= candle_data[-1]["open"] else "bearish"

    last_c = candle_data[-1]["close"]
    body = avg_body * 0.8
    wick = avg_range * 0.3
    if direction == "bullish":
        proj_close = last_c + body
        proj_high = proj_close + wick
        proj_low = last_c - wick * 0.5
    else:
        proj_close = last_c - body
        proj_high = last_c + wick * 0.5
        proj_low = proj_close - wick

    return jsonify({
        "projection": {
            "time": (candle_data[-1].get("time", 0) or 0) + 86400,
            "open": round(last_c, 6),
            "high": round(proj_high, 6),
            "low": round(proj_low, 6),
            "close": round(proj_close, 6),
            "direction": direction,
            "confidence": round(max(bullish_votes, bearish_votes) / len(predictions), 2) if predictions else 0.5,
        },
        "votes": {"bullish": bullish_votes, "bearish": bearish_votes, "total": len(predictions)},
        "triggers": predictions,
        "fallback": fallback,
    })


def _get_candle(candles, offset):
    """Get candle by negative offset (e.g., -1 = last, -2 = second-to-last)."""
    idx = len(candles) + offset
    if idx < 0 or idx >= len(candles):
        return None
    return candles[idx]


def _wick_upper(c):
    return c["high"] - max(c["open"], c["close"])


def _wick_lower(c):
    return min(c["open"], c["close"]) - c["low"]


def _body(c):
    return abs(c["close"] - c["open"])


def _range(c):
    return c["high"] - c["low"]


def evaluate_rule(conditions, candles):
    if isinstance(conditions, dict) and conditions.get("version") == 2:
        return _evaluate_v2(conditions, candles)
    return _evaluate_v1(conditions, candles)


def _evaluate_v1(conditions, candles):
    """Old simple format: list of {type, value} conditions."""
    last = candles[-1]
    second_last = candles[-2] if len(candles) >= 2 else None
    third_last = candles[-3] if len(candles) >= 3 else None
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
            rng = _range(last)
            if rng > 0 and _wick_upper(last) / rng >= ratio:
                triggered.append("bearish")
        elif t == "long_lower_wick":
            ratio = val if val else 0.5
            rng = _range(last)
            if rng > 0 and _wick_lower(last) / rng >= ratio:
                triggered.append("bullish")
        elif t == "volume_spike":
            mult = val if val else 2.0
            vol = last.get("volume", 0)
            if vol and len(candles) >= 5:
                avg_vol = statistics.mean([c.get("volume", 0) for c in candles[-6:-1]])
                if avg_vol > 0 and vol / avg_vol >= mult:
                    triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "marubozu":
            rng = _range(last)
            if rng > 0 and _body(last) / rng >= 0.85:
                triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "doji":
            rng = _range(last)
            if rng > 0 and _body(last) / rng <= 0.1:
                triggered.append("bullish" if last["close"] >= last["open"] else "bearish")
        elif t == "engulfing":
            if third_last and second_last:
                curr_body = _body(last)
                prev_body = _body(second_last)
                if curr_body > prev_body * 1.2:
                    prev_dir = second_last["close"] >= second_last["open"]
                    curr_dir = last["close"] >= last["open"]
                    if prev_dir != curr_dir:
                        triggered.append("bullish" if curr_dir else "bearish")
    if not triggered:
        return None
    bullish = sum(1 for t in triggered if t == "bullish")
    bearish = sum(1 for t in triggered if t == "bearish")
    return {"direction": "bullish" if bullish >= bearish else "bearish", "triggered": triggered}


def _evaluate_v2(config, candles):
    """New structured format: {version:2, conditions:[...], action:'bullish'|'bearish'}."""
    conditions = config.get("conditions", [])
    action = config.get("action", "bullish")

    for cond in conditions:
        ctype = cond.get("type")
        params = cond.get("params", {})

        if ctype == "pattern":
            consecutive = params.get("consecutive", 1)
            direction = params.get("direction")
            if len(candles) < consecutive:
                return None
            for i in range(consecutive):
                c = candles[-(i + 1)]
                if direction == "bearish" and c["close"] >= c["open"]:
                    return None
                if direction == "bullish" and c["close"] < c["open"]:
                    return None

        elif ctype == "wick_comparison":
            ca = _get_candle(candles, params["candle_a"])
            cb = _get_candle(candles, params["candle_b"])
            if ca is None or cb is None:
                return None
            part = params.get("part", "upper")
            comp = params.get("comparison", "gt")
            if part == "upper":
                va, vb = _wick_upper(ca), _wick_upper(cb)
            else:
                va, vb = _wick_lower(ca), _wick_lower(cb)
            if comp == "gt" and not (va < vb):
                return None
            if comp == "lt" and not (va > vb):
                return None
            if comp == "gte" and not (va <= vb):
                return None
            if comp == "lte" and not (va >= vb):
                return None

        elif ctype == "body_ratio":
            c = _get_candle(candles, params.get("candle", -1))
            if c is None:
                return None
            comp = params.get("comparison", "gte")
            val = params.get("value", 0.5)
            rng = _range(c)
            if rng == 0:
                return None
            ratio = _body(c) / rng
            if comp == "gte" and not (ratio >= val):
                return None
            if comp == "lte" and not (ratio <= val):
                return None

        elif ctype == "volume_ratio":
            c = _get_candle(candles, params.get("candle", -1))
            if c is None:
                return None
            mult = params.get("multiplier", 2.0)
            comp = params.get("comparison", "gte")
            vol = c.get("volume", 0)
            if not vol or len(candles) < 5:
                return None
            avg_vol = statistics.mean(
                [x.get("volume", 0) for x in candles[-6:-1] if x.get("volume", 0) > 0]
            )
            if avg_vol == 0:
                return None
            if comp == "gte" and not (vol / avg_vol >= mult):
                return None
            if comp == "lte" and not (vol / avg_vol <= mult):
                return None

        elif ctype == "marubozu":
            c = _get_candle(candles, params.get("candle", -1))
            if c is None:
                return None
            threshold = params.get("threshold", 0.85)
            rng = _range(c)
            if rng == 0 or _body(c) / rng < threshold:
                return None

        elif ctype == "doji":
            c = _get_candle(candles, params.get("candle", -1))
            if c is None:
                return None
            threshold = params.get("threshold", 0.1)
            rng = _range(c)
            if rng == 0 or _body(c) / rng > threshold:
                return None

        elif ctype == "engulfing":
            if len(candles) < 2:
                return None
            ca = candles[-2]
            cb = candles[-1]
            curr_body = _body(cb)
            prev_body = _body(ca)
            if curr_body <= prev_body * (params.get("min_mult", 1.2)):
                return None
            prev_dir = ca["close"] >= ca["open"]
            curr_dir = cb["close"] >= cb["open"]
            if prev_dir == curr_dir:
                return None

        elif ctype == "consecutive_direction":
            c = _get_candle(candles, params.get("candle", -1))
            if c is None:
                return None
            n = params.get("lookback", 2)
            if len(candles) < n:
                return None
            direction = params.get("direction", "bearish")
            for i in range(n):
                cc = candles[-(i + 1)]
                if direction == "bearish" and cc["close"] >= cc["open"]:
                    return None
                if direction == "bullish" and cc["close"] < cc["open"]:
                    return None

    return {"direction": action, "triggered": [c.get("type") for c in conditions]}
