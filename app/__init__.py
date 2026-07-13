import os
import tempfile
from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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
    login_manager.init_app(app)

    from app.utils.storage import init_storage
    init_storage(app)

    from app.routes import register_blueprints
    register_blueprints(app)

    @app.before_request
    def load_current_org():
        from flask import session as flask_session
        from flask_login import current_user
        org_id = flask_session.get("org_id")
        if current_user.is_authenticated and org_id:
            org = current_user.organizations.filter_by(id=org_id).first()
            g.current_org = org
        else:
            g.current_org = None

    @app.context_processor
    def inject_notification_count():
        from flask_login import current_user
        from app.models import Notification
        try:
            if current_user.is_authenticated:
                count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
                return {"unread_notifications_count": count}
        except (RuntimeError, AttributeError):
            pass
        return {"unread_notifications_count": 0}

    if not app.config.get("TESTING") and not app.config.get("SCHEDULER_DISABLED"):
        _init_scheduler(app)

    return app


def _init_scheduler(app):
    sched = BackgroundScheduler(daemon=True)
    from app.routes.scheduler import scheduler_tick
    sched.add_job(
        scheduler_tick,
        trigger=IntervalTrigger(minutes=1),
        args=[app],
        id="scheduler_tick",
        name="Check and run due schedulers",
        replace_existing=True,
    )
    sched.start()
    app.scheduler = sched
