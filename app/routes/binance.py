import requests
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from app.utils.auth import org_required

binance_bp = Blueprint("binance", __name__)

BINANCE_API = "https://api.binance.com"


@binance_bp.route("/binance")
@login_required
@org_required
def index():
    return render_template("binance_chart.html")


@binance_bp.route("/binance/api/klines")
@login_required
@org_required
def klines():
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    interval = request.args.get("interval", "1h")
    limit = request.args.get("limit", "100")

    try:
        limit = int(limit)
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000
    except ValueError:
        limit = 100

    try:
        resp = requests.get(
            f"{BINANCE_API}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    candles = []
    for k in data:
        candles.append({
            "time": k[0] // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })

    return jsonify({"symbol": symbol, "interval": interval, "candles": candles})
