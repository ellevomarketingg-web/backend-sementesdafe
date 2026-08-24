"""add_order_bumps

Revision ID: 002_add_order_bumps
Revises: 001_initial
Create Date: 2026-08-24 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_add_order_bumps'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'order_bumps',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('buyer_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=True),
        sa.Column('product_id', sa.String(length=128), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=False),
        sa.Column('product_code', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='UNLOCKED'),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('download_url', sa.String(length=512), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unlocked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata_info', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_bumps_buyer_id'), 'order_bumps', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_order_bumps_order_id'), 'order_bumps', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_bumps_product_id'), 'order_bumps', ['product_id'], unique=False)
    op.create_index(op.f('ix_order_bumps_status'), 'order_bumps', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_order_bumps_status'), table_name='order_bumps')
    op.drop_index(op.f('ix_order_bumps_product_id'), table_name='order_bumps')
    op.drop_index(op.f('ix_order_bumps_order_id'), table_name='order_bumps')
    op.drop_index(op.f('ix_order_bumps_buyer_id'), table_name='order_bumps')
    op.drop_table('order_bumps')
