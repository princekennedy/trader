"""Add object_name to extraction_jobs

Revision ID: 22070bbc7e03
Revises: 
Create Date: 2026-07-07 09:16:05.926319

"""
from alembic import op
import sqlalchemy as sa


revision = '22070bbc7e03'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("extraction_jobs")]
    if "object_name" not in columns:
        with op.batch_alter_table("extraction_jobs", schema=None) as batch_op:
            batch_op.add_column(sa.Column("object_name", sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table("extraction_jobs", schema=None) as batch_op:
        batch_op.drop_column("object_name")
