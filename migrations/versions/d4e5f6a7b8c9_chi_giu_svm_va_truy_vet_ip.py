"""chi giu mo hinh TF-IDF + SVM + truy vet IP ke lua dao

- Xoa du lieu cua "the gioi" phobert / viso (2 mo hinh da bo): users (cascade), guardian_events.
- Them: messages.sender_ip / sender_user_agent; bang login_logs, scam_traces, trace_requests.

Revision ID: d4e5f6a7b8c9
Revises: c7a1d2e3f4b5
Create Date: 2026-11-07 15:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c7a1d2e3f4b5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM guardian_events WHERE model_key <> 'svm'")
    op.execute("DELETE FROM users WHERE model_key <> 'svm'")

    op.add_column('messages', sa.Column('sender_ip', sa.String(length=45), nullable=True))
    op.add_column('messages', sa.Column('sender_user_agent', sa.String(length=255), nullable=True))

    op.create_table('login_logs',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('ip', sa.String(length=45), nullable=True),
                    sa.Column('user_agent', sa.String(length=255), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_login_logs_user', 'login_logs', ['user_id', 'id'])
    op.create_index('ix_login_logs_created', 'login_logs', ['created_at'])

    op.create_table('scam_traces',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('model_key', sa.String(length=20), nullable=False),
                    sa.Column('offender_id', sa.Integer(), nullable=True),
                    sa.Column('victim_id', sa.Integer(), nullable=True),
                    sa.Column('conversation_id', sa.Integer(), nullable=True),
                    sa.Column('offender_username', sa.String(length=30), nullable=False),
                    sa.Column('offender_name', sa.String(length=80), nullable=False),
                    sa.Column('victim_username', sa.String(length=30), nullable=False),
                    sa.Column('victim_name', sa.String(length=80), nullable=False),
                    sa.Column('block_nth', sa.SmallInteger(), nullable=False),
                    sa.Column('ip', sa.String(length=45), nullable=True),
                    sa.Column('user_agent', sa.String(length=255), nullable=True),
                    sa.Column('country', sa.String(length=80), nullable=True),
                    sa.Column('region', sa.String(length=120), nullable=True),
                    sa.Column('city', sa.String(length=120), nullable=True),
                    sa.Column('isp', sa.String(length=160), nullable=True),
                    sa.Column('geo_source', sa.String(length=10), nullable=False),
                    sa.Column('evidence', sa.JSON(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.ForeignKeyConstraint(['offender_id'], ['users.id'], ondelete='SET NULL'),
                    sa.ForeignKeyConstraint(['victim_id'], ['users.id'], ondelete='SET NULL'),
                    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
                    sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_scam_traces_offender_id', 'scam_traces', ['offender_id'])
    op.create_index('ix_scam_traces_victim_id', 'scam_traces', ['victim_id'])
    op.create_index('ix_scam_traces_ip', 'scam_traces', ['ip'])
    op.create_index('ix_scam_traces_model', 'scam_traces', ['model_key', 'id'])

    op.create_table('trace_requests',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('trace_id', sa.Integer(), nullable=False),
                    sa.Column('requester_id', sa.Integer(), nullable=False),
                    sa.Column('reason', sa.String(length=500), nullable=False),
                    sa.Column('status', sa.String(length=10), nullable=False),
                    sa.Column('admin_note', sa.String(length=500), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('resolved_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['trace_id'], ['scam_traces.id'], ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_trace_requests_trace_id', 'trace_requests', ['trace_id'])
    op.create_index('ix_trace_requests_requester_id', 'trace_requests', ['requester_id'])
    op.create_index('ix_trace_requests_status', 'trace_requests', ['status', 'id'])


def downgrade():
    op.drop_table('trace_requests')
    op.drop_table('scam_traces')
    op.drop_table('login_logs')
    op.drop_column('messages', 'sender_user_agent')
    op.drop_column('messages', 'sender_ip')
