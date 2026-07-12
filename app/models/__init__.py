import secrets
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

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("organization_id", db.Integer, db.ForeignKey("organizations.id"), primary_key=True),
)


class User(UserMixin, db.Model, AuditMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)

    organizations = db.relationship("Organization", secondary=user_organizations, lazy="dynamic", overlaps="users")
    created_orgs = db.relationship("Organization", foreign_keys="Organization.owner_id", back_populates="owner", lazy="dynamic")
    roles = db.relationship("Role", secondary=user_roles, lazy="dynamic", overlaps="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_token(self):
        self.api_token = secrets.token_hex(32)
        return self.api_token

    def regenerate_api_token(self):
        return self.generate_api_token()

    def has_permission(self, permission_slug, org_id=None):
        if org_id is None:
            from flask import g
            org = g.get("current_org")
            if not org:
                return False
            org_id = org.id
        org = Organization.query.get(org_id)
        if org and org.owner_id == self.id:
            return True
        for role in self.roles.filter(user_roles.c.organization_id == org_id).all():
            if role.is_system:
                return True
            for perm in role.permissions:
                if perm.slug == permission_slug:
                    return True
        return False


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
    roles = db.relationship("Role", back_populates="organization", lazy="dynamic")


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="", nullable=False)
    module = db.Column(db.String(50), default="", nullable=False, index=True)


class Role(db.Model, AuditMixin):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, default="", nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True)
    is_system = db.Column(db.Boolean, default=False, nullable=False)

    organization = db.relationship("Organization", back_populates="roles")
    permissions = db.relationship("Permission", secondary=role_permissions, lazy="dynamic")
    users = db.relationship("User", secondary=user_roles, lazy="dynamic", overlaps="roles")

    __table_args__ = (
        db.UniqueConstraint("slug", "organization_id", name="uq_role_slug_org"),
    )


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


class AIProvider(db.Model):
    __tablename__ = "ai_providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    base_url = db.Column(db.String(500), nullable=False)
    chat_endpoint = db.Column(db.String(200), nullable=False, default="/chat/completions")
    default_model = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    models = db.relationship("AIProviderModel", back_populates="provider", lazy="dynamic")


class AIProviderModel(db.Model):
    __tablename__ = "ai_provider_models"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("ai_providers.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    provider = db.relationship("AIProvider", back_populates="models")


class AIKey(db.Model, AuditMixin):
    __tablename__ = "ai_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("ai_providers.id"), nullable=False, index=True)
    api_key = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Rule(db.Model, AuditMixin):
    __tablename__ = "rules"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="", nullable=False)
    conditions = db.Column(db.JSON, default=list, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    organization = db.relationship("Organization", foreign_keys=[organization_id])


scheduler_rules = db.Table(
    "scheduler_rules",
    db.Column("scheduler_id", db.Integer, db.ForeignKey("schedulers.id"), primary_key=True),
    db.Column("rule_id", db.Integer, db.ForeignKey("rules.id"), primary_key=True),
)


class Scheduler(db.Model, AuditMixin):
    __tablename__ = "schedulers"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    source_type = db.Column(db.String(20), nullable=False, default="binance")  # binance or image
    source_config = db.Column(db.JSON, default=dict, nullable=False)
    schedule_time = db.Column(db.Time, nullable=False)
    email_recipients = db.Column(db.JSON, default=list, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_run_at = db.Column(db.DateTime, nullable=True)

    organization = db.relationship("Organization", foreign_keys=[organization_id])
    rules = db.relationship("Rule", secondary=scheduler_rules, lazy="dynamic")


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", uselist=False)
