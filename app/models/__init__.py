from app import db


class ExtractionJob(db.Model):
    __tablename__ = "extraction_jobs"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    symbol = db.Column(db.String(20), default="")
    timeframe = db.Column(db.String(10), default="")
    status = db.Column(db.String(20), default="pending")
    candle_count = db.Column(db.Integer, default=0)
    quality_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())


class Candle(db.Model):
    __tablename__ = "candles"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("extraction_jobs.id"), nullable=False)
    index = db.Column(db.Integer, nullable=False)
    direction = db.Column(db.String(10))
    open = db.Column(db.Float)
    high = db.Column(db.Float)
    low = db.Column(db.Float)
    close = db.Column(db.Float)
    volume = db.Column(db.Float)
    body = db.Column(db.Float)
    upper_wick = db.Column(db.Float)
    lower_wick = db.Column(db.Float)
    confidence = db.Column(db.Float, default=1.0)

    job = db.relationship("ExtractionJob", backref=db.backref("candles", lazy="dynamic"))


class Strategy(db.Model):
    __tablename__ = "strategies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    config = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
