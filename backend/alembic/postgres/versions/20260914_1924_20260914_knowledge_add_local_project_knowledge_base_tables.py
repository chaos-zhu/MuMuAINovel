"""add local project knowledge base tables

Revision ID: 20260914_knowledge
Revises: f0e1d2c3b4a5
Create Date: 2026-09-14 19:24:35.040020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260914_knowledge'
down_revision: Union[str, None] = 'f0e1d2c3b4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_bases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_knowledge_bases_project_id'),
        'knowledge_bases',
        ['project_id'],
        unique=False,
    )
    op.create_index(op.f('ix_knowledge_bases_status'), 'knowledge_bases', ['status'], unique=False)
    op.create_index(
        op.f('ix_knowledge_bases_user_id'),
        'knowledge_bases',
        ['user_id'],
        unique=False,
    )
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('knowledge_base_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('source_type', sa.String(length=30), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('parser_name', sa.String(length=100), nullable=True),
        sa.Column('parser_version', sa.String(length=30), nullable=True),
        sa.Column('document_version', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('extracted_char_count', sa.Integer(), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=False),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_knowledge_documents_knowledge_base_id'),
        'knowledge_documents',
        ['knowledge_base_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_documents_project_id'),
        'knowledge_documents',
        ['project_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_documents_sha256'),
        'knowledge_documents',
        ['sha256'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_documents_status'),
        'knowledge_documents',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_documents_user_id'),
        'knowledge_documents',
        ['user_id'],
        unique=False,
    )
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('knowledge_base_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section_title', sa.String(length=300), nullable=True),
        sa.Column('heading_path', sa.JSON(), nullable=True),
        sa.Column('start_offset', sa.Integer(), nullable=True),
        sa.Column('end_offset', sa.Integer(), nullable=True),
        sa.Column('vector_id', sa.String(length=100), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('embedding_dimension', sa.Integer(), nullable=True),
        sa.Column('index_status', sa.String(length=20), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vector_id'),
    )
    op.create_index(
        op.f('ix_knowledge_chunks_content_hash'),
        'knowledge_chunks',
        ['content_hash'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunks_document_id'),
        'knowledge_chunks',
        ['document_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunks_index_status'),
        'knowledge_chunks',
        ['index_status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunks_knowledge_base_id'),
        'knowledge_chunks',
        ['knowledge_base_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunks_project_id'),
        'knowledge_chunks',
        ['project_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunks_user_id'),
        'knowledge_chunks',
        ['user_id'],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_chunks_user_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_project_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_knowledge_base_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_index_status'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_document_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_content_hash'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_documents_user_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_status'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_sha256'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_project_id'), table_name='knowledge_documents')
    op.drop_index(
        op.f('ix_knowledge_documents_knowledge_base_id'),
        table_name='knowledge_documents',
    )
    op.drop_table('knowledge_documents')
    op.drop_index(op.f('ix_knowledge_bases_user_id'), table_name='knowledge_bases')
    op.drop_index(op.f('ix_knowledge_bases_status'), table_name='knowledge_bases')
    op.drop_index(op.f('ix_knowledge_bases_project_id'), table_name='knowledge_bases')
    op.drop_table('knowledge_bases')
