"""initial_schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-08-24 13:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Buyers
    op.create_table(
        'buyers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('email_normalized', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('generation_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_buyers_email_normalized'), 'buyers', ['email_normalized'], unique=True)

    # Orders
    op.create_table(
        'orders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('external_order_id', sa.String(length=128), nullable=False),
        sa.Column('buyer_id', sa.String(length=36), nullable=False),
        sa.Column('product_code', sa.String(length=64), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_info', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orders_buyer_id'), 'orders', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_orders_external_order_id'), 'orders', ['external_order_id'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)

    # Book Templates
    op.create_table(
        'book_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('template_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'version', name='uq_book_template_name_version'),
    )

    # Books
    op.create_table(
        'books',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('buyer_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=False),
        sa.Column('child_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('file_url', sa.String(length=512), nullable=True),
        sa.Column('generation_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['book_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_books_buyer_id'), 'books', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_books_order_id'), 'books', ['order_id'], unique=True)
    op.create_index(op.f('ix_books_status'), 'books', ['status'], unique=False)

    # Communication Templates
    op.create_table(
        'communication_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'channel', 'version', name='uq_comm_template_code_channel_version'),
    )
    op.create_index(op.f('ix_communication_templates_code'), 'communication_templates', ['code'], unique=False)
    op.create_index(op.f('ix_communication_templates_event'), 'communication_templates', ['event'], unique=False)

    # Messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('buyer_id', sa.String(length=36), nullable=False),
        sa.Column('book_id', sa.String(length=36), nullable=True),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('destination', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('external_message_id', sa.String(length=255), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['communication_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_messages_book_id'), 'messages', ['book_id'], unique=False)
    op.create_index(op.f('ix_messages_buyer_id'), 'messages', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_messages_external_message_id'), 'messages', ['external_message_id'], unique=False)
    op.create_index(op.f('ix_messages_status'), 'messages', ['status'], unique=False)

    # Deliveries
    op.create_table(
        'deliveries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('book_id', sa.String(length=36), nullable=False),
        sa.Column('buyer_id', sa.String(length=36), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=False),
        sa.Column('delivery_url', sa.String(length=512), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deliveries_book_id'), 'deliveries', ['book_id'], unique=False)
    op.create_index(op.f('ix_deliveries_buyer_id'), 'deliveries', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_deliveries_status'), 'deliveries', ['status'], unique=False)

    # Processed Events (Idempotency)
    op.create_table(
        'processed_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_processed_events_event_id'), 'processed_events', ['event_id'], unique=True)
    op.create_index(op.f('ix_processed_events_event_type'), 'processed_events', ['event_type'], unique=False)

    # Verification Codes (2FA)
    op.create_table(
        'verification_codes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email_normalized', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_verification_codes_email_normalized'), 'verification_codes', ['email_normalized'], unique=False)


def downgrade() -> None:
    op.drop_table('verification_codes')
    op.drop_table('processed_events')
    op.drop_table('deliveries')
    op.drop_table('messages')
    op.drop_table('communication_templates')
    op.drop_table('books')
    op.drop_table('book_templates')
    op.drop_table('orders')
    op.drop_table('buyers')
