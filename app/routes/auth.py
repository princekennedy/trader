from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("org.select"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash("Welcome back!", "success")
            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            first_org = user.organizations.first()
            if first_org:
                session["org_id"] = first_org.id
                return redirect(url_for("main.dashboard"))
            return redirect(url_for("org.create"))
        flash("Invalid email or password", "error")
    return render_template("auth_login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields are required", "error")
            return render_template("auth_register.html")
        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("auth_register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters", "error")
            return render_template("auth_register.html")
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("auth_register.html")

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created! Now create your organization.", "success")
        return redirect(url_for("org.create"))
    return render_template("auth_register.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    session.pop("org_id", None)
    flash("Logged out", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            flash("If that email exists, a reset link has been sent (demo mode).", "success")
        else:
            flash("If that email exists, a reset link has been sent (demo mode).", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth_forgot.html")
