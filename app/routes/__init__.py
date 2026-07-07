def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.org import org_bp
    from app.routes.main import main_bp
    from app.routes.charts import charts_bp
    from app.routes.data import data_bp
    from app.routes.ai import ai_bp
    from app.routes.api import api_bp
    from app.routes.roles import roles_bp
    from app.routes.users_mgmt import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(org_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(charts_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(users_bp)

    from app.commands import seed_command
    app.cli.add_command(seed_command)
