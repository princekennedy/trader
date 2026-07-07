from datetime import datetime, timedelta
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, PasswordResetToken
from app.utils.email import send_welcome_email, send_password_reset_email


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("org.select"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password", "error")
            return render_template("auth_login.html")
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
        send_welcome_email(user)
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
            existing = PasswordResetToken.query.filter_by(user_id=user.id, used=False).filter(
                PasswordResetToken.expires_at > datetime.utcnow()
            ).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
            token_str = secrets.token_urlsafe(48)
            token = PasswordResetToken(
                user_id=user.id,
                token=token_str,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.session.add(token)
            db.session.commit()
            reset_url = url_for("auth.reset_password", token=token_str, _external=True)
            send_password_reset_email(user, reset_url)
        flash("If that email exists, a reset link has been sent.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth_forgot.html")


@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
        token_record = PasswordResetToken.query.filter_by(token=token, used=False).filter(
            PasswordResetToken.expires_at > datetime.utcnow()
        ).first()
        if not token_record:
            flash("Invalid or expired reset link", "error")
            return redirect(url_for("auth.login"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not password or len(password) < 6:
                flash("Password must be at least 6 characters", "error")
                return render_template("auth_reset_password.html", token=token)
            if password != confirm:
                flash("Passwords do not match", "error")
                return render_template("auth_reset_password.html", token=token)

            user = User.query.get(token_record.user_id)
            if not user:
                flash("User not found", "error")
                return redirect(url_for("auth.login"))

            user.set_password(password)
            token_record.used = True
            db.session.commit()

            flash("Password reset successfully! Please sign in.", "success")
            return redirect(url_for("auth.login"))

        return render_template("auth_reset_password.html", token=token)
