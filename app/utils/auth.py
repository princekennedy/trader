from functools import wraps
from flask import abort, redirect, url_for, session, current_app, g
from flask_login import current_user


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def org_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        org_id = session.get("org_id")
        if not org_id:
            return redirect(url_for("org.select"))
        org = current_user.organizations.filter_by(id=org_id).first()
        if not org:
            return redirect(url_for("org.select"))
        g.current_org = org
        return f(*args, **kwargs)
    return decorated


def current_org():
    return g.get("current_org")
