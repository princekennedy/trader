import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, session as flask_session
from flask_login import current_user
from app import db
from app.models import Organization, User, Role, user_organizations, user_roles
from app.utils.auth import login_required as auth_required

org_bp = Blueprint("org", __name__, url_prefix="/org")


def slugify(name):
    s = name.lower().replace(" ", "-").replace("_", "-")
    return re.sub(r"[^a-z0-9-]", "", s)


def _set_audit_fields(record):
    if current_user.is_authenticated:
        record.created_by_id = current_user.id


def _set_audit_updated(record):
    if current_user.is_authenticated:
        record.updated_by_id = current_user.id


@org_bp.route("/select")
@auth_required
def select():
    orgs = current_user.organizations.all()
    return render_template("org_select.html", organizations=orgs)


@org_bp.route("/create", methods=["GET", "POST"])
@auth_required
def create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Organization name is required", "error")
            return render_template("org_create.html")

        slug = slugify(name)
        if not slug:
            flash("Invalid organization name", "error")
            return render_template("org_create.html")

        existing = Organization.query.filter_by(slug=slug).first()
        if existing:
            flash("An organization with this name already exists", "error")
            return render_template("org_create.html")

        org = Organization(name=name, slug=slug, description=description, owner_id=current_user.id)
        _set_audit_fields(org)
        db.session.add(org)
        db.session.flush()

        stmt = user_organizations.insert().values(
            user_id=current_user.id, organization_id=org.id, role="admin"
        )
        db.session.execute(stmt)

        admin_role = Role.query.filter_by(slug="admin", is_system=True).first()
        if admin_role:
            db.session.execute(
                user_roles.insert().values(
                    user_id=current_user.id, role_id=admin_role.id, organization_id=org.id
                )
            )
        db.session.commit()

        flask_session["org_id"] = org.id
        flash(f"Organization '{name}' created!", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("org_create.html")


@org_bp.route("/<int:org_id>/switch")
@auth_required
def switch(org_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for("org.select"))
    flask_session["org_id"] = org.id
    flash(f"Switched to {org.name}", "success")
    return redirect(url_for("main.dashboard"))


@org_bp.route("/<int:org_id>/settings", methods=["GET", "POST"])
@auth_required
def settings(org_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for("org.select"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            org.name = name
            _set_audit_updated(org)
            db.session.commit()
            flash("Organization updated", "success")
        return redirect(url_for("org.settings", org_id=org.id))

    members = db.session.query(User, user_organizations.c.role).join(
        user_organizations, User.id == user_organizations.c.user_id
    ).filter(
        user_organizations.c.organization_id == org.id
    ).all()

    return render_template("org_settings.html", org=org, members=members)


@org_bp.route("/<int:org_id>/members/add", methods=["POST"])
@auth_required
def add_member(org_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org or org.owner_id != current_user.id:
        flash("Only the organization owner can add members", "error")
        return redirect(url_for("org.settings", org_id=org_id))

    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "member")
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found", "error")
        return redirect(url_for("org.settings", org_id=org_id))

    existing = db.session.execute(
        user_organizations.select().where(
            user_organizations.c.user_id == user.id,
            user_organizations.c.organization_id == org_id,
        )
    ).first()
    if existing:
        flash("User is already a member", "error")
        return redirect(url_for("org.settings", org_id=org_id))

    stmt = user_organizations.insert().values(
        user_id=user.id, organization_id=org.id, role=role
    )
    db.session.execute(stmt)
    db.session.commit()
    flash(f"Added {user.name} as {role}", "success")
    return redirect(url_for("org.settings", org_id=org_id))


@org_bp.route("/<int:org_id>/members/<int:user_id>/remove", methods=["POST"])
@auth_required
def remove_member(org_id, user_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org or org.owner_id != current_user.id:
        flash("Only the organization owner can remove members", "error")
        return redirect(url_for("org.settings", org_id=org_id))

    if user_id == current_user.id:
        flash("You cannot remove yourself", "error")
        return redirect(url_for("org.settings", org_id=org_id))

    stmt = user_organizations.delete().where(
        user_organizations.c.user_id == user_id,
        user_organizations.c.organization_id == org_id,
    )
    db.session.execute(stmt)
    db.session.commit()
    flash("Member removed", "success")
    return redirect(url_for("org.settings", org_id=org_id))


@org_bp.route("/<int:org_id>/edit", methods=["GET", "POST"])
@auth_required
def edit(org_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for("org.select"))

    if org.owner_id != current_user.id:
        flash("Only the owner can edit the organization", "error")
        return redirect(url_for("org.settings", org_id=org.id))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Organization name is required", "error")
            return render_template("org_edit.html", org=org)
        org.name = name
        org.description = description
        _set_audit_updated(org)
        db.session.commit()
        flash("Organization updated!", "success")
        return redirect(url_for("org.settings", org_id=org.id))

    return render_template("org_edit.html", org=org)


@org_bp.route("/<int:org_id>/delete", methods=["POST"])
@auth_required
def delete(org_id):
    org = current_user.organizations.filter_by(id=org_id).first()
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for("org.select"))

    if org.owner_id != current_user.id:
        flash("Only the owner can delete the organization", "error")
        return redirect(url_for("org.settings", org_id=org.id))

    from flask import session as flask_session

    stmt = user_organizations.delete().where(
        user_organizations.c.organization_id == org.id,
    )
    db.session.execute(stmt)
    db.session.delete(org)
    db.session.commit()

    flask_session.pop("org_id", None)
    flash("Organization deleted", "success")
    return redirect(url_for("org.select"))
