from functools import wraps
from flask import abort, g
from flask_login import current_user


def permission_required(slug):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            org = g.get("current_org")
            if not org:
                abort(403, description="No organization selected")
            if not current_user.has_permission(slug, org.id):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def has_permission(slug):
    org = g.get("current_org")
    if not org:
        return False
    return current_user.has_permission(slug, org.id)


PERMISSIONS = [
    {"name": "Create Jobs", "slug": "jobs.create", "module": "jobs", "description": "Upload chart images and create extraction jobs"},
    {"name": "View Jobs", "slug": "jobs.read", "module": "jobs", "description": "View extraction jobs"},
    {"name": "Update Jobs", "slug": "jobs.update", "module": "jobs", "description": "Reprocess extraction jobs"},
    {"name": "Delete Jobs", "slug": "jobs.delete", "module": "jobs", "description": "Delete extraction jobs"},
    {"name": "View Organization", "slug": "org.view", "module": "org", "description": "View organization settings and details"},
    {"name": "Edit Organization", "slug": "org.edit", "module": "org", "description": "Edit organization settings"},
    {"name": "Delete Organization", "slug": "org.delete", "module": "org", "description": "Delete the organization"},
    {"name": "Manage Members", "slug": "org.manage_members", "module": "org", "description": "Add and remove organization members"},
    {"name": "Create Roles", "slug": "roles.create", "module": "roles", "description": "Create new roles"},
    {"name": "View Roles", "slug": "roles.read", "module": "roles", "description": "View roles"},
    {"name": "Update Roles", "slug": "roles.update", "module": "roles", "description": "Edit roles and their permissions"},
    {"name": "Delete Roles", "slug": "roles.delete", "module": "roles", "description": "Delete roles"},
    {"name": "View Permissions", "slug": "permissions.read", "module": "permissions", "description": "View the permissions list"},
    {"name": "View Users", "slug": "users.read", "module": "users", "description": "View organization users"},
    {"name": "Manage User Roles", "slug": "users.manage_roles", "module": "users", "description": "Assign roles to users"},
    {"name": "Use AI", "slug": "ai.use", "module": "ai", "description": "Use AI detection features"},
    {"name": "View Settings", "slug": "settings.view", "module": "settings", "description": "View user settings"},
    {"name": "Edit Settings", "slug": "settings.edit", "module": "settings", "description": "Edit user settings"},
]
