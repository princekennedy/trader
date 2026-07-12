import requests
from datetime import datetime, time as dtime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_required, current_user
from app import db
from app.models import Organization, Rule, ExtractionJob, Scheduler
from app.utils.auth import org_required
from app.routes.predict import evaluate_rule
from app.utils.email import send_email

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/scheduler")

BINANCE_API = "https://api.binance.com"


@scheduler_bp.route("/")
@login_required
@org_required
def index():
    schedulers = Scheduler.query.filter_by(
        organization_id=g.current_org.id
    ).order_by(Scheduler.created_at.desc()).all()
    return render_template("scheduler.html", schedulers=schedulers)


@scheduler_bp.route("/create", methods=["GET", "POST"])
@login_required
@org_required
def create():
    if request.method == "GET":
        rules = Rule.query.filter_by(
            organization_id=g.current_org.id, is_active=True
        ).all()
        jobs = ExtractionJob.query.filter_by(
            organization_id=g.current_org.id
        ).order_by(ExtractionJob.created_at.desc()).limit(50).all()
        return render_template("scheduler_form.html", scheduler=None, rules=rules, jobs=jobs)

    data = request.form
    name = data.get("name", "").strip()
    source_type = data.get("source_type", "binance")
    schedule_hr = data.get("schedule_hour", "09")
    schedule_min = data.get("schedule_minute", "00")
    recipient_str = data.get("email_recipients", "").strip()
    rule_ids = request.form.getlist("rule_ids")

    if not name:
        flash("Name is required", "danger")
        return redirect(url_for("scheduler.create"))
    if not rule_ids:
        flash("Select at least one rule", "danger")
        return redirect(url_for("scheduler.create"))

    if source_type == "binance":
        symbol = data.get("symbol", "BTCUSDT").upper().strip()
        interval = data.get("interval", "1h")
        lookback = int(data.get("lookback", "50"))
        source_config = {"symbol": symbol, "interval": interval, "lookback": lookback}
    elif source_type == "image":
        job_id = data.get("job_id", "").strip()
        if not job_id:
            flash("Select an extraction job for image source", "danger")
            return redirect(url_for("scheduler.create"))
        source_config = {"job_id": int(job_id)}
    else:
        flash("Invalid source type", "danger")
        return redirect(url_for("scheduler.create"))

    recipients = [r.strip() for r in recipient_str.split(",") if r.strip()]
    if not recipients:
        flash("At least one email recipient is required", "danger")
        return redirect(url_for("scheduler.create"))

    try:
        schedule_time = dtime(int(schedule_hr), int(schedule_min))
    except ValueError:
        flash("Invalid schedule time", "danger")
        return redirect(url_for("scheduler.create"))

    scheduler = Scheduler(
        organization_id=g.current_org.id,
        name=name,
        source_type=source_type,
        source_config=source_config,
        schedule_time=schedule_time,
        email_recipients=recipients,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.session.add(scheduler)
    db.session.flush()

    for rid in rule_ids:
        rule = Rule.query.filter_by(id=int(rid), organization_id=g.current_org.id).first()
        if rule:
            scheduler.rules.append(rule)

    db.session.commit()
    flash("Scheduler created", "success")
    return redirect(url_for("scheduler.index"))


@scheduler_bp.route("/<int:sched_id>/edit", methods=["GET", "POST"])
@login_required
@org_required
def edit(sched_id):
    scheduler = Scheduler.query.filter_by(
        id=sched_id, organization_id=g.current_org.id
    ).first_or_404()

    if request.method == "GET":
        rules = Rule.query.filter_by(
            organization_id=g.current_org.id, is_active=True
        ).all()
        jobs = ExtractionJob.query.filter_by(
            organization_id=g.current_org.id
        ).order_by(ExtractionJob.created_at.desc()).limit(50).all()
        selected_ids = [r.id for r in scheduler.rules]
        return render_template(
            "scheduler_form.html", scheduler=scheduler, rules=rules,
            jobs=jobs, selected_ids=selected_ids
        )

    data = request.form
    scheduler.name = data.get("name", "").strip()
    scheduler.source_type = data.get("source_type", "binance")
    schedule_hr = data.get("schedule_hour", "09")
    schedule_min = data.get("schedule_minute", "00")
    recipient_str = data.get("email_recipients", "").strip()
    rule_ids = request.form.getlist("rule_ids")

    if not scheduler.name:
        flash("Name is required", "danger")
        return redirect(url_for("scheduler.edit", sched_id=sched_id))

    if scheduler.source_type == "binance":
        symbol = data.get("symbol", "BTCUSDT").upper().strip()
        interval = data.get("interval", "1h")
        lookback = int(data.get("lookback", "50"))
        scheduler.source_config = {"symbol": symbol, "interval": interval, "lookback": lookback}
    elif scheduler.source_type == "image":
        job_id = data.get("job_id", "").strip()
        scheduler.source_config = {"job_id": int(job_id)} if job_id else {}

    scheduler.email_recipients = [r.strip() for r in recipient_str.split(",") if r.strip()]
    try:
        scheduler.schedule_time = dtime(int(schedule_hr), int(schedule_min))
    except ValueError:
        flash("Invalid schedule time", "danger")
        return redirect(url_for("scheduler.edit", sched_id=sched_id))

    scheduler.rules = []
    for rid in rule_ids:
        rule = Rule.query.filter_by(id=int(rid), organization_id=g.current_org.id).first()
        if rule:
            scheduler.rules.append(rule)

    scheduler.updated_by_id = current_user.id
    db.session.commit()
    flash("Scheduler updated", "success")
    return redirect(url_for("scheduler.index"))


@scheduler_bp.route("/<int:sched_id>/delete", methods=["POST"])
@login_required
@org_required
def delete(sched_id):
    scheduler = Scheduler.query.filter_by(
        id=sched_id, organization_id=g.current_org.id
    ).first_or_404()
    db.session.delete(scheduler)
    db.session.commit()
    flash("Scheduler deleted", "success")
    return redirect(url_for("scheduler.index"))


@scheduler_bp.route("/<int:sched_id>/toggle", methods=["POST"])
@login_required
@org_required
def toggle(sched_id):
    scheduler = Scheduler.query.filter_by(
        id=sched_id, organization_id=g.current_org.id
    ).first_or_404()
    scheduler.is_active = not scheduler.is_active
    scheduler.updated_by_id = current_user.id
    db.session.commit()
    return jsonify({"ok": True, "is_active": scheduler.is_active})


def _fetch_binance_candles(symbol, interval, limit):
    try:
        resp = requests.get(
            f"{BINANCE_API}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None

    return [{
        "time": k[0] // 1000,
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
    } for k in data]


def scheduler_tick(app):
    with app.app_context():
        now = datetime.now()
        current_time = now.time()
        today = now.date()

        due = Scheduler.query.filter(
            Scheduler.is_active == True,
            Scheduler.schedule_time <= current_time,
            (Scheduler.last_run_at == None) | (db.func.date(Scheduler.last_run_at) < today),
        ).all()

        for sched in due:
            try:
                _run_scheduler(sched)
                sched.last_run_at = now
                db.session.commit()
            except Exception as e:
                app.logger.error("Scheduler %d tick error: %s", sched.id, e)


def _run_scheduler(sched):
    candles = None

    if sched.source_type == "binance":
        cfg = sched.source_config
        candles = _fetch_binance_candles(
            cfg.get("symbol", "BTCUSDT"),
            cfg.get("interval", "1h"),
            cfg.get("lookback", 50),
        )
    elif sched.source_type == "image":
        job_id = sched.source_config.get("job_id")
        if job_id:
            from app.models import Candle
            candle_rows = Candle.query.filter_by(job_id=job_id).order_by(Candle.index.asc()).all()
            if candle_rows:
                candles = [
                    {"open": c.open, "high": c.high, "low": c.low,
                     "close": c.close, "volume": c.volume or 0, "time": 0}
                    for c in candle_rows
                ]

    if not candles or len(candles) < 3:
        return

    bullish_votes = 0
    bearish_votes = 0
    for rule in sched.rules:
        result = evaluate_rule(rule.conditions, candles)
        if result is not None:
            triggered = result.get("triggered")
            if triggered:
                if result["direction"] == "bullish":
                    bullish_votes += 1
                else:
                    bearish_votes += 1

    if bullish_votes > bearish_votes:
        _send_alert(sched, candles, bullish_votes, bearish_votes)


def _send_alert(sched, candles, bullish_votes, bearish_votes):
    last = candles[-1]
    source_label = sched.source_config.get("symbol", "chart") if sched.source_type == "binance" else f"job #{sched.source_config.get('job_id', '?')}"
    rule_names = [r.name for r in sched.rules]

    for email in sched.email_recipients:
        html = render_template(
            "emails/bullish_alert.html",
            scheduler_name=sched.name,
            source_label=source_label,
            source_type=sched.source_type,
            last_close=last["close"],
            rule_count=len(sched.rules),
            rule_names=rule_names,
            bullish_votes=bullish_votes,
            bearish_votes=bearish_votes,
        )
        send_email(email, f"[Bullish Alert] {sched.name} - {source_label}", html)
