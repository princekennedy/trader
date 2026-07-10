import click
from flask.cli import with_appcontext
from app import db
from app.models import Permission, Role, role_permissions, AIProvider, AIProviderModel


def seed_permissions():
    from app.utils.permissions import PERMISSIONS
    count = 0
    for p in PERMISSIONS:
        existing = Permission.query.filter_by(slug=p["slug"]).first()
        if not existing:
            db.session.add(Permission(name=p["name"], slug=p["slug"], module=p["module"], description=p["description"]))
            count += 1
    if count:
        db.session.commit()
    return count


def seed_roles():
    from app.utils.permissions import PERMISSIONS

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
    admin_perm_ids = {p.id for p in admin.permissions}
    for perm in all_perms:
        if perm.id not in admin_perm_ids:
            admin.permissions.append(perm)

    member_slugs = {"jobs.create", "jobs.read", "ai.use", "org.view", "roles.read", "permissions.read", "users.read", "settings.view"}
    member_perm_ids = {p.id for p in member.permissions}
    for perm in all_perms:
        if perm.slug in member_slugs and perm.id not in member_perm_ids:
            member.permissions.append(perm)

    db.session.commit()


def seed_ai_providers():
    providers = [
        {
            "name": "OpenAI", "slug": "openai",
            "base_url": "https://api.openai.com/v1",
            "chat_endpoint": "/chat/completions",
            "default_model": "gpt-4o",
            "models": [
                {"name": "GPT-4o", "slug": "gpt-4o"},
                {"name": "GPT-4o Mini", "slug": "gpt-4o-mini"},
                {"name": "GPT-4 Turbo", "slug": "gpt-4-turbo"},
                {"name": "GPT-3.5 Turbo", "slug": "gpt-3.5-turbo"},
            ],
        },
        {
            "name": "Gemini", "slug": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "chat_endpoint": "/models/{model}:generateContent",
            "default_model": "gemini-2.0-flash",
            "models": [
                {"name": "Gemini 2.0 Flash", "slug": "gemini-2.0-flash"},
                {"name": "Gemini 2.0 Pro", "slug": "gemini-2.0-pro"},
                {"name": "Gemini 1.5 Pro", "slug": "gemini-1.5-pro"},
                {"name": "Gemini 1.5 Flash", "slug": "gemini-1.5-flash"},
            ],
        },
        {
            "name": "Grok", "slug": "grok",
            "base_url": "https://api.x.ai/v1",
            "chat_endpoint": "/chat/completions",
            "default_model": "grok-2",
            "models": [
                {"name": "Grok 2", "slug": "grok-2"},
                {"name": "Grok 2 Mini", "slug": "grok-2-mini"},
                {"name": "Grok Beta", "slug": "grok-beta"},
            ],
        },
    ]
    count = 0
    for pdata in providers:
        provider = AIProvider.query.filter_by(slug=pdata["slug"]).first()
        if not provider:
            provider = AIProvider(
                name=pdata["name"], slug=pdata["slug"],
                base_url=pdata["base_url"], chat_endpoint=pdata["chat_endpoint"],
                default_model=pdata["default_model"],
            )
            db.session.add(provider)
            db.session.flush()
            count += 1
        for mdata in pdata["models"]:
            existing = AIProviderModel.query.filter_by(provider_id=provider.id, slug=mdata["slug"]).first()
            if not existing:
                db.session.add(AIProviderModel(
                    provider_id=provider.id, name=mdata["name"], slug=mdata["slug"]
                ))
    if count:
        db.session.commit()
    return count


@click.command("seed")
@with_appcontext
def seed_command():
    click.echo("Seeding permissions...")
    created = seed_permissions()
    click.echo(f"  Created {created} new permission(s)")
    click.echo("Seeding roles...")
    seed_roles()
    click.echo("Seeding AI providers...")
    pcount = seed_ai_providers()
    click.echo(f"  Created {pcount} new provider(s)")
    click.echo("Done! Permissions, roles, and AI providers are ready.")
