def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.org import org_bp
    from app.routes.main import main_bp
    from app.routes.charts import charts_bp
    from app.routes.data import data_bp
    from app.routes.rules import rules_bp
    from app.routes.api import api_bp
    from app.routes.roles import roles_bp
    from app.routes.users_mgmt import users_bp
    from app.routes.binance import binance_bp
    from app.routes.predict import predict_bp
    from app.routes.scheduler import scheduler_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(org_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(charts_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(binance_bp)
    app.register_blueprint(predict_bp)
    app.register_blueprint(scheduler_bp)

    from app.commands import seed_command
    app.cli.add_command(seed_command)
