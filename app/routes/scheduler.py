import requests
from datetime import datetime, time as dtime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_required, current_user
from app import db
from app.models import Organization, Rule, ExtractionJob, Scheduler, Notification
from app.utils.auth import org_required
from app.routes.predict import evaluate_rule
from app.utils.email import send_email

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/scheduler")

BINANCE_API = "https://api.binance.com"

SCHEDULE_TYPES = {
    "interval": "Every N minutes/hours/days/weeks",
    "daily": "Daily at specific time",
    "weekly": "Weekly on specific day & time",
    "monthly": "Monthly on specific day & time",
}

NOTIFY_OPTIONS = {
    "bullish": "Bullish only",
    "bearish": "Bearish only",
    "both": "Both bullish and bearish",
}


@scheduler_bp.route("/")
@login_required
@org_required
def index():
    schedulers = Scheduler.query.filter_by(
        organization_id=g.current_org.id
    ).order_by(Scheduler.created_at.desc()).all()
    return render_template("scheduler.html", schedulers=schedulers,
                           notify_options=NOTIFY_OPTIONS,
                           schedule_label=_get_schedule_label)


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

    notify_on = data.get("notify_on", "bullish")
    if notify_on not in ("bullish", "bearish", "both"):
        notify_on = "bullish"

    schedule_type = data.get("schedule_type", "daily")
    schedule_config = _build_schedule_config(data, schedule_type)
    if schedule_config is None:
        return redirect(url_for("scheduler.create"))

    scheduler = Scheduler(
        organization_id=g.current_org.id,
        name=name,
        source_type=source_type,
        source_config=source_config,
        schedule_config=schedule_config,
        notify_on=notify_on,
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

    notify_on = data.get("notify_on", "bullish")
    scheduler.notify_on = notify_on if notify_on in ("bullish", "bearish", "both") else "bullish"

    schedule_type = data.get("schedule_type", "daily")
    schedule_config = _build_schedule_config(data, schedule_type)
    if schedule_config is None:
        return redirect(url_for("scheduler.edit", sched_id=sched_id))
    scheduler.schedule_config = schedule_config

    scheduler.email_recipients = [r.strip() for r in data.get("email_recipients", "").split(",") if r.strip()]

    scheduler.rules = []
    for rid in request.form.getlist("rule_ids"):
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


def _build_schedule_config(data, schedule_type):
    if schedule_type == "interval":
        try:
            value = int(data.get("interval_value", "60"))
            if value < 1:
                value = 1
        except ValueError:
            flash("Invalid interval value", "danger")
            return None
        unit = data.get("interval_unit", "minutes")
        if unit not in ("minutes", "hours", "days", "weeks"):
            unit = "minutes"
        return {"type": "interval", "value": value, "unit": unit}

    hr = data.get("schedule_hour", "09")
    minute = data.get("schedule_minute", "00")
    try:
        time_str = f"{int(hr):02d}:{int(minute):02d}"
    except ValueError:
        flash("Invalid schedule time", "danger")
        return None

    if schedule_type == "daily":
        return {"type": "daily", "time": time_str}
    elif schedule_type == "weekly":
        day = data.get("schedule_day", "1")
        try:
            day = int(day)
        except ValueError:
            day = 1
        return {"type": "weekly", "time": time_str, "day": day}
    elif schedule_type == "monthly":
        day = data.get("schedule_day", "1")
        try:
            day = int(day)
            if day < 1 or day > 31:
                day = 1
        except ValueError:
            day = 1
        return {"type": "monthly", "time": time_str, "day": day}
    else:
        flash("Invalid schedule type", "danger")
        return None


def _get_schedule_label(sc):
    if not sc:
        return "Unknown"
    st = sc.get("type", "daily")
    if st == "interval":
        return f"Every {sc['value']} {sc.get('unit', 'minutes')}"
    time_str = sc.get("time", "09:00")
    if st == "daily":
        return f"Daily at {time_str}"
    if st == "weekly":
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_label = days[sc.get("day", 1) % 7]
        return f"{day_label} at {time_str}"
    if st == "monthly":
        return f"Day {sc.get('day', 1)} at {time_str}"
    return "Unknown"


# ---- Binance fetching ----

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


# ---- Scheduler tick / background ----

def scheduler_tick(app):
    with app.app_context():
        now = datetime.now()
        due = Scheduler.query.filter(Scheduler.is_active == True).all()

        for sched in due:
            if _is_due(sched, now):
                try:
                    _run_scheduler(sched)
                    sched.last_run_at = now
                    db.session.commit()
                except Exception as e:
                    app.logger.error("Scheduler %d tick error: %s", sched.id, e)


def _is_due(sched, now):
    sc = sched.schedule_config or {}
    st = sc.get("type", "daily")

    if st == "interval":
        value = sc.get("value", 60)
        unit = sc.get("unit", "minutes")
        if sched.last_run_at is None:
            return True
        delta = timedelta(**{unit: value})
        return (now - sched.last_run_at) >= delta

    current_time = now.time()
    target_time = _parse_time(sc.get("time", "09:00"))
    if target_time is None:
        return False
    if current_time < target_time:
        return False

    if st == "weekly":
        day = sc.get("day", 1) % 7
        if now.weekday() != day:
            return False
    elif st == "monthly":
        day = sc.get("day", 1)
        if now.day != day:
            return False

    last = sched.last_run_at
    if last is None:
        return True
    return last.date() < now.date()


def _parse_time(t):
    try:
        parts = t.split(":")
        return dtime(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


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

    notify = sched.notify_on or "bullish"
    should_send = (
        (notify == "bullish" and bullish_votes > bearish_votes) or
        (notify == "bearish" and bearish_votes > bullish_votes) or
        (notify == "both" and bullish_votes != bearish_votes)
    )
    if should_send:
        _send_alert(sched, candles, bullish_votes, bearish_votes)


def _send_alert(sched, candles, bullish_votes, bearish_votes):
    last = candles[-1]
    source_label = sched.source_config.get("symbol", "chart") if sched.source_type == "binance" else f"job #{sched.source_config.get('job_id', '?')}"
    rule_names = [r.name for r in sched.rules]
    direction = "bullish" if bullish_votes > bearish_votes else "bearish"

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
        subject = f"[{direction.title()} Alert] {sched.name} - {source_label}"
        send_email(email, subject, html)

    user_id = sched.created_by_id
    if user_id:
        notif = Notification(
            user_id=user_id,
            organization_id=sched.organization_id,
            title=f"{direction.title()} Alert",
            message=f"Scheduler \"{sched.name}\" detected {bullish_votes}B / {bearish_votes}B on {source_label}",
            type=direction,
            link="/scheduler/",
        )
        db.session.add(notif)
        db.session.commit()
