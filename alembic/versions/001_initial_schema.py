"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Customers Table
    op.create_table(
        'customers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('external_id')
    )
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=True)
    op.create_index(op.f('ix_customers_external_id'), 'customers', ['external_id'], unique=True)

    # 2. AWS Accounts Table
    op.create_table(
        'aws_accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=12), nullable=False),
        sa.Column('role_arn', sa.String(length=255), nullable=False),
        sa.Column('alias', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aws_accounts_customer_id'), 'aws_accounts', ['customer_id'], unique=False)

    # 3. Scan Jobs Table
    op.create_table(
        'scan_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('aws_account_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('total_resources_scanned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_savings_identified', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['aws_account_id'], ['aws_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scan_jobs_aws_account_id'), 'scan_jobs', ['aws_account_id'], unique=False)
    op.create_index(op.f('ix_scan_jobs_customer_id'), 'scan_jobs', ['customer_id'], unique=False)

    # 4. Pull Request Logs Table
    op.create_table(
        'pull_request_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('scan_job_id', sa.String(length=36), nullable=True),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('original_spec', sa.String(length=100), nullable=False),
        sa.Column('proposed_spec', sa.String(length=100), nullable=False),
        sa.Column('monthly_savings_usd', sa.Float(), nullable=False),
        sa.Column('pr_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='created'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scan_job_id'], ['scan_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pull_request_logs_customer_id'), 'pull_request_logs', ['customer_id'], unique=False)
    op.create_index(op.f('ix_pull_request_logs_scan_job_id'), 'pull_request_logs', ['scan_job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pull_request_logs_scan_job_id'), table_name='pull_request_logs')
    op.drop_index(op.f('ix_pull_request_logs_customer_id'), table_name='pull_request_logs')
    op.drop_table('pull_request_logs')

    op.drop_index(op.f('ix_scan_jobs_customer_id'), table_name='scan_jobs')
    op.drop_index(op.f('ix_scan_jobs_aws_account_id'), table_name='scan_jobs')
    op.drop_table('scan_jobs')

    op.drop_index(op.f('ix_aws_accounts_customer_id'), table_name='aws_accounts')
    op.drop_table('aws_accounts')

    op.drop_index(op.f('ix_customers_external_id'), table_name='customers')
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_table('customers')
