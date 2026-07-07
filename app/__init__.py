import os
import tempfile
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///trading.db"
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    upload_folder = os.getenv(
        "UPLOAD_FOLDER", os.path.join(app.root_path, "..", "uploads")
    )
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["TEMP_FOLDER"] = os.getenv(
        "TEMP_FOLDER", tempfile.gettempdir()
    )

    db.init_app(app)
    migrate.init_app(app, db)

    from app.utils.storage import init_storage
    init_storage(app)

    from app.routes import register_blueprints
    register_blueprints(app)

    with app.app_context():
        db.create_all()

    return app
