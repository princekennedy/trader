import click
from flask.cli import with_appcontext
from app import db
from app.models import Permission, Role, role_permissions


def seed_permissions():
    from app.utils.permissions import PERMISSIONS
    for p in PERMISSIONS:
        existing = Permission.query.filter_by(slug=p["slug"]).first()
        if not existing:
            db.session.add(Permission(name=p["name"], slug=p["slug"], module=p["module"], description=p["description"]))
    db.session.commit()


def seed_roles():
    admin = Role.query.filter_by(slug="admin", is_system=True).first()
    if not admin:
        admin = Role(name="Admin", slug="admin", description="System administrator with full access", is_system=True)
        db.session.add(admin)
        db.session.flush()

    member = Role.query.filter_by(slug="member", is_system=True).first()
    if not member:
        member = Role(name="Member", slug="member", description="Standard organization member", is_system=True)
        db.session.add(member)
        db.session.flush()

    all_perms = Permission.query.all()
    for perm in all_perms:
        if perm not in admin.permissions.all():
            admin.permissions.append(perm)

    member_slugs = {"jobs.create", "jobs.read", "ai.use", "org.view", "roles.read", "permissions.read", "users.read", "settings.view"}
    for perm in all_perms:
        if perm.slug in member_slugs and perm not in member.permissions.all():
            member.permissions.append(perm)

    db.session.commit()


@click.command("seed")
@with_appcontext
def seed_command():
    click.echo("Seeding permissions...")
    seed_permissions()
    click.echo("Seeding roles...")
    seed_roles()
    click.echo("Done! Created permissions and default roles (Admin, Member).")
