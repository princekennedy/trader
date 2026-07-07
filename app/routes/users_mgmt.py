from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import current_user
from app import db
from app.models import User, Role, user_roles, user_organizations
from app.utils.auth import login_required, org_required
from app.utils.permissions import permission_required

users_bp = Blueprint("users", __name__, url_prefix="/org/<int:org_id>/users")


@users_bp.before_request
def load_org():
    from flask import session as flask_session
    org_id = flask_session.get("org_id")
    if current_user.is_authenticated and org_id:
        org = current_user.organizations.filter_by(id=org_id).first()
        g.current_org = org


@users_bp.route("")
@login_required
@org_required
@permission_required("users.read")
def list_users(org_id):
    org = g.current_org
    members = db.session.query(User, user_organizations.c.role).join(
        user_organizations, User.id == user_organizations.c.user_id
    ).filter(
        user_organizations.c.organization_id == org.id
    ).all()

    user_role_map = {}
    for m, _ in members:
        assigned_roles = db.session.query(Role).join(
            user_roles, Role.id == user_roles.c.role_id
        ).filter(
            user_roles.c.user_id == m.id,
            user_roles.c.organization_id == org.id,
        ).all()
        user_role_map[m.id] = assigned_roles

    return render_template("users/list.html", org=org, members=members, user_role_map=user_role_map)


@users_bp.route("/<int:user_id>/roles", methods=["GET", "POST"])
@login_required
@org_required
@permission_required("users.manage_roles")
def manage_roles(org_id, user_id):
    org = g.current_org
    user = User.query.get_or_404(user_id)

    membership = db.session.execute(
        user_organizations.select().where(
            user_organizations.c.user_id == user.id,
            user_organizations.c.organization_id == org.id,
        )
    ).first()
    if not membership:
        flash("User is not a member of this organization", "error")
        return redirect(url_for("users.list_users", org_id=org.id))

    if request.method == "POST":
        role_ids = request.form.getlist("role_ids", type=int)
        db.session.execute(
            user_roles.delete().where(
                user_roles.c.user_id == user.id,
                user_roles.c.organization_id == org.id,
            )
        )
        for rid in role_ids:
            role = Role.query.filter_by(id=rid).first()
            if role and (role.organization_id == org.id or role.is_system):
                db.session.execute(
                    user_roles.insert().values(user_id=user.id, role_id=rid, organization_id=org.id)
                )
        db.session.commit()
        flash(f"Roles updated for {user.name}", "success")
        return redirect(url_for("users.list_users", org_id=org.id))

    available_roles = Role.query.filter(
        (Role.organization_id == org.id) | (Role.is_system == True)
    ).all()

    current_role_ids = [
        r[0] for r in db.session.execute(
            user_roles.select().where(
                user_roles.c.user_id == user.id,
                user_roles.c.organization_id == org.id,
            )
        ).all()
    ]

    return render_template(
        "users/roles.html", org=org, target_user=user,
        available_roles=available_roles, current_role_ids=set(current_role_ids),
    )
