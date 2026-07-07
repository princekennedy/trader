from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class AuditMixin:
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now(), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    @db.declared_attr
    def created_by(cls):
        return db.relationship("User", foreign_keys=[cls.created_by_id], remote_side="User.id", uselist=False)

    @db.declared_attr
    def updated_by(cls):
        return db.relationship("User", foreign_keys=[cls.updated_by_id], remote_side="User.id", uselist=False)


user_organizations = db.Table(
    "user_organizations",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("organization_id", db.Integer, db.ForeignKey("organizations.id"), primary_key=True),
    db.Column("role", db.String(20), default="member", nullable=False),
    db.Column("created_at", db.DateTime, server_default=db.func.now(), nullable=False),
)


class User(UserMixin, db.Model, AuditMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    organizations = db.relationship("Organization", secondary=user_organizations, lazy="dynamic", overlaps="users")
    created_orgs = db.relationship("Organization", foreign_keys="Organization.owner_id", back_populates="owner", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Organization(db.Model, AuditMixin):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="", nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    owner = db.relationship("User", foreign_keys=[owner_id], back_populates="created_orgs", uselist=False)
    users = db.relationship("User", secondary=user_organizations, lazy="dynamic", overlaps="organizations")
    extraction_jobs = db.relationship("ExtractionJob", back_populates="organization", lazy="dynamic")
    strategies = db.relationship("Strategy", back_populates="organization", lazy="dynamic")


class ExtractionJob(db.Model, AuditMixin):
    __tablename__ = "extraction_jobs"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    object_name = db.Column(db.String(500), default="", nullable=False)
    symbol = db.Column(db.String(20), default="", nullable=False, index=True)
    timeframe = db.Column(db.String(10), default="", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    candle_count = db.Column(db.Integer, default=0, nullable=False)
    quality_score = db.Column(db.Float, default=0.0, nullable=False)
    error_message = db.Column(db.Text, nullable=True)

    organization = db.relationship("Organization", back_populates="extraction_jobs")
    candles = db.relationship("Candle", back_populates="job", lazy="dynamic", cascade="all, delete-orphan")


class Candle(db.Model, AuditMixin):
    __tablename__ = "candles"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("extraction_jobs.id"), nullable=False, index=True)
    index = db.Column(db.Integer, nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    open = db.Column(db.Float, nullable=False)
    high = db.Column(db.Float, nullable=False)
    low = db.Column(db.Float, nullable=False)
    close = db.Column(db.Float, nullable=False)
    volume = db.Column(db.Float, nullable=True)
    body = db.Column(db.Float, nullable=False)
    upper_wick = db.Column(db.Float, nullable=False)
    lower_wick = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Float, default=1.0, nullable=False)

    job = db.relationship("ExtractionJob", back_populates="candles")

    __table_args__ = (
        db.UniqueConstraint("job_id", "index", name="uq_candle_job_index"),
    )


class Strategy(db.Model, AuditMixin):
    __tablename__ = "strategies"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="", nullable=False)
    config = db.Column(db.JSON, default=dict, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    organization = db.relationship("Organization", back_populates="strategies")
