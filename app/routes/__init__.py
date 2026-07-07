def register_blueprints(app):
    from app.routes.main import main_bp
    from app.routes.charts import charts_bp
    from app.routes.data import data_bp
    from app.routes.ai import ai_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(charts_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(ai_bp)
