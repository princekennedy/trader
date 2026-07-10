"""add ai provider tables

Revision ID: a1b2c3d4e5f6
Revises: 558f442589c4
Create Date: 2026-07-10 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a1b2c3d4e5f6'
down_revision = '558f442589c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ai_providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('chat_endpoint', sa.String(length=200), nullable=False, server_default='/chat/completions'),
        sa.Column('default_model', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_providers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_providers_slug'), ['slug'], unique=True)

    op.create_table('ai_provider_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['provider_id'], ['ai_providers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_provider_models', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_provider_models_provider_id'), ['provider_id'], unique=False)

    op.create_table('ai_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('api_key', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['provider_id'], ['ai_providers.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_keys_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_keys_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_keys_provider_id'), ['provider_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ai_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_keys_provider_id'))
        batch_op.drop_index(batch_op.f('ix_ai_keys_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ai_keys_user_id'))
    op.drop_table('ai_keys')
    with op.batch_alter_table('ai_provider_models', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_provider_models_provider_id'))
    op.drop_table('ai_provider_models')
    with op.batch_alter_table('ai_providers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_providers_slug'))
    op.drop_table('ai_providers')
