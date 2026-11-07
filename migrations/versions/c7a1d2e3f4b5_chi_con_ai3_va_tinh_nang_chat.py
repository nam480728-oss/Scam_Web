"""chi con AI 3 (bo deepfake, Agent 2, bo cong cu) + tinh nang chat moi

- Xoa: bang call_verdicts, blacklist_entries; cot users.agent1_enabled / agent2_enabled / avatar_hash,
  avatar_history.phash, messages.attachment_sha256, calls.simulated / ended_by_guardian,
  guardian_events.call_id / agent3_needed, reports.call_id, feedback.call_id,
  appeal_captures.deepfake_score / deepfake_mode.
- Them: messages.reply_to_id / recalled_at / pinned_at / pinned_by_id, bang message_reactions.

Revision ID: c7a1d2e3f4b5
Revises: bc3f49fdf4cd
Create Date: 2026-10-25 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7a1d2e3f4b5'
down_revision = 'bc3f49fdf4cd'
branch_labels = None
depends_on = None


def _drop_fk_and_column(table: str, column: str):
    """MySQL: phai bo khoa ngoai (ten tu sinh) truoc khi bo cot."""
    insp = sa.inspect(op.get_bind())
    for fk in insp.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column] and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
    op.drop_column(table, column)


def upgrade():
    op.drop_table('call_verdicts')
    op.drop_table('blacklist_entries')
    with op.batch_alter_table('users') as b:
        b.drop_column('agent1_enabled')
        b.drop_column('agent2_enabled')
        b.drop_column('avatar_hash')
    op.drop_column('avatar_history', 'phash')
    op.drop_column('messages', 'attachment_sha256')
    op.drop_column('calls', 'simulated')
    op.drop_column('calls', 'ended_by_guardian')
    _drop_fk_and_column('guardian_events', 'call_id')
    op.drop_column('guardian_events', 'agent3_needed')
    _drop_fk_and_column('reports', 'call_id')
    _drop_fk_and_column('feedback', 'call_id')
    op.drop_column('appeal_captures', 'deepfake_score')
    op.drop_column('appeal_captures', 'deepfake_mode')

    op.add_column('messages', sa.Column('reply_to_id', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('recalled_at', sa.DateTime(), nullable=True))
    op.add_column('messages', sa.Column('pinned_at', sa.DateTime(), nullable=True))
    op.add_column('messages', sa.Column('pinned_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_messages_reply_to', 'messages', 'messages', ['reply_to_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_messages_pinned_by', 'messages', 'users', ['pinned_by_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_messages_pinned', 'messages', ['conversation_id', 'pinned_at'])
    op.create_table('message_reactions',
                    sa.Column('message_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('emoji', sa.String(length=16), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('message_id', 'user_id'))


def downgrade():
    op.drop_table('message_reactions')
    op.drop_index('ix_messages_pinned', table_name='messages')
    op.drop_constraint('fk_messages_pinned_by', 'messages', type_='foreignkey')
    op.drop_constraint('fk_messages_reply_to', 'messages', type_='foreignkey')
    for col in ('pinned_by_id', 'pinned_at', 'recalled_at', 'reply_to_id'):
        op.drop_column('messages', col)

    op.add_column('appeal_captures', sa.Column('deepfake_mode', sa.String(length=12), nullable=True))
    op.add_column('appeal_captures', sa.Column('deepfake_score', sa.Float(), nullable=True))
    op.add_column('feedback', sa.Column('call_id', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('call_id', sa.Integer(), nullable=True))
    op.add_column('guardian_events', sa.Column('agent3_needed', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('guardian_events', sa.Column('call_id', sa.Integer(), nullable=True))
    op.add_column('calls', sa.Column('ended_by_guardian', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('calls', sa.Column('simulated', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('messages', sa.Column('attachment_sha256', sa.String(length=64), nullable=True))
    op.add_column('avatar_history', sa.Column('phash', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('avatar_hash', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('agent2_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.add_column('users', sa.Column('agent1_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.create_table('blacklist_entries',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('kind', sa.String(length=20), nullable=False),
                    sa.Column('value', sa.String(length=255), nullable=False),
                    sa.Column('source', sa.String(length=20), nullable=False),
                    sa.Column('reason', sa.String(length=300), nullable=True),
                    sa.Column('added_by', sa.Integer(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.ForeignKeyConstraint(['added_by'], ['users.id'], ondelete='SET NULL'),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('kind', 'value', name='uq_blacklist_kind_value'))
    op.create_table('call_verdicts',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('call_id', sa.Integer(), nullable=False),
                    sa.Column('max_face', sa.Float(), nullable=False),
                    sa.Column('max_voice', sa.Float(), nullable=False),
                    sa.Column('max_behavior', sa.Float(), nullable=False),
                    sa.Column('max_combined', sa.Float(), nullable=False),
                    sa.Column('speech_risk', sa.Float(), nullable=True),
                    sa.Column('speech_scenario', sa.String(length=40), nullable=True),
                    sa.Column('deepfake_detected', sa.Boolean(), nullable=False),
                    sa.Column('ended_by_guardian', sa.Boolean(), nullable=False),
                    sa.Column('challenge', sa.String(length=12), nullable=True),
                    sa.Column('mode', sa.String(length=12), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('call_id'))
