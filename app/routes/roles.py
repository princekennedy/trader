import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import current_user
from app import db
from app.models import Role, Permission
from app.utils.auth import login_required, org_required
from app.utils.permissions import permission_required

roles_bp = Blueprint("roles", __name__, url_prefix="/org/<int:org_id>/roles")


def _slugify(name):
    s = name.lower().replace(" ", "-").replace("_", "-")
    return re.sub(r"[^a-z0-9-]", "", s)


@roles_bp.route("")
@login_required
@org_required
def list_roles(org_id):
    org = g.current_org
    roles = Role.query.filter(
        (Role.organization_id == org.id) | (Role.is_system == True)
    ).order_by(Role.is_system.desc(), Role.name).all()
    return render_template("roles/list.html", org=org, roles=roles)


@roles_bp.route("/create", methods=["GET", "POST"])
@login_required
@org_required
@permission_required("roles.create")
def create_role(org_id):
    org = g.current_org
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        perm_slugs = request.form.getlist("permissions")
        if not name:
            flash("Role name is required", "error")
            return redirect(url_for("roles.create_role", org_id=org.id))

        slug = _slugify(name)
        if not slug:
            flash("Invalid role name", "error")
            return redirect(url_for("roles.create_role", org_id=org.id))

        existing = Role.query.filter_by(slug=slug, organization_id=org.id).first()
        if existing:
            flash("A role with this name already exists", "error")
            return redirect(url_for("roles.create_role", org_id=org.id))

        role = Role(name=name, slug=slug, description=description, organization_id=org.id)
        db.session.add(role)
        db.session.flush()

        perms = Permission.query.filter(Permission.slug.in_(perm_slugs)).all()
        for p in perms:
            role.permissions.append(p)

        db.session.commit()
        flash(f"Role '{name}' created!", "success")
        return redirect(url_for("roles.list_roles", org_id=org.id))

    permissions = Permission.query.order_by(Permission.module, Permission.name).all()
    return render_template("roles/form.html", org=org, role=None, permissions=permissions, selected=set())


@roles_bp.route("/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
@org_required
@permission_required("roles.update")
def edit_role(org_id, role_id):
    org = g.current_org
    role = Role.query.filter_by(id=role_id, organization_id=org.id).first()
    if not role:
        flash("Role not found", "error")
        return redirect(url_for("roles.list_roles", org_id=org.id))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        perm_slugs = request.form.getlist("permissions")
        if not name:
            flash("Role name is required", "error")
            return redirect(url_for("roles.edit_role", org_id=org.id, role_id=role.id))

        role.name = name
        role.description = description

        role.permissions = []
        perms = Permission.query.filter(Permission.slug.in_(perm_slugs)).all()
        for p in perms:
            role.permissions.append(p)

        db.session.commit()
        flash(f"Role '{name}' updated!", "success")
        return redirect(url_for("roles.list_roles", org_id=org.id))

    permissions = Permission.query.order_by(Permission.module, Permission.name).all()
    selected = {p.slug for p in role.permissions}
    return render_template("roles/form.html", org=org, role=role, permissions=permissions, selected=selected)


@roles_bp.route("/<int:role_id>/delete", methods=["POST"])
@login_required
@org_required
@permission_required("roles.delete")
def delete_role(org_id, role_id):
    org = g.current_org
    role = Role.query.filter_by(id=role_id, organization_id=org.id).first()
    if not role:
        flash("Role not found", "error")
        return redirect(url_for("roles.list_roles", org_id=org.id))

    db.session.delete(role)
    db.session.commit()
    flash(f"Role '{role.name}' deleted!", "success")
    return redirect(url_for("roles.list_roles", org_id=org.id))


@roles_bp.route("/permissions")
@login_required
@org_required
def list_permissions(org_id):
    permissions = Permission.query.order_by(Permission.module, Permission.name).all()
    return render_template("permissions.html", org=g.current_org, permissions=permissions)
