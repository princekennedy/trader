"""Add schedule_config and notify_on to schedulers

Revision ID: abd9c21f9623
Revises: 0dee1c970681
Create Date: 2026-07-13 04:12:41.748469

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'abd9c21f9623'
down_revision = '0dee1c970681'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('schedulers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('schedule_config', sa.JSON(),
                            server_default=sa.text("'{\"type\": \"daily\", \"time\": \"09:00\"}'::json"),
                            nullable=False))
        batch_op.add_column(sa.Column('notify_on', sa.String(length=20),
                            server_default=sa.text("'bullish'"),
                            nullable=False))
        batch_op.alter_column('schedule_time',
               existing_type=postgresql.TIME(),
               nullable=True)

    op.execute("""
        UPDATE schedulers
        SET schedule_config = json_build_object('type', 'daily', 'time', to_char(schedule_time, 'HH24:MI'))
        WHERE schedule_time IS NOT NULL
    """)


def downgrade():
    with op.batch_alter_table('schedulers', schema=None) as batch_op:
        batch_op.alter_column('schedule_time',
               existing_type=postgresql.TIME(),
               nullable=False)
        batch_op.drop_column('notify_on')
        batch_op.drop_column('schedule_config')
