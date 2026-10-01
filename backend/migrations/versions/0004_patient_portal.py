"""Отдельные учётные записи и зашифрованные анкеты пациентов."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = depends_on = None


def upgrade():
    op.create_table('portal_accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('login_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('profile', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False))
    op.create_table('portal_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('portal_accounts.id'), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False))
    op.create_index('ix_portal_sessions_account_id', 'portal_sessions', ['account_id'])
    op.create_table('patient_intakes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('portal_accounts.id'), nullable=False),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id'), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('encounter_id', sa.String(36), sa.ForeignKey('encounters.id')),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False))
    for column in ('account_id', 'doctor_id', 'encounter_id'):
        op.create_index('ix_patient_intakes_' + column, 'patient_intakes', [column])
    op.create_table('intake_invites',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id'), nullable=False),
        sa.Column('script', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('portal_accounts.id')))
    op.create_index('ix_intake_invites_doctor_id', 'intake_invites', ['doctor_id'])
    if op.get_bind().dialect.name == 'postgresql':
        for table in ('portal_accounts', 'portal_sessions', 'patient_intakes', 'intake_invites'):
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
            for role in ('anon', 'authenticated'):
                op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}')
                    THEN REVOKE ALL ON {table} FROM {role}; END IF; END $$""")


def downgrade():
    for table in ('intake_invites', 'patient_intakes', 'portal_sessions', 'portal_accounts'):
        op.drop_table(table)
