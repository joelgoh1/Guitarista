"""noodle mode tables: spotify_auth, listening_pool

Revision ID: 0002_noodle
Revises: 0001_initial
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_noodle"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spotify_auth",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("spotify_user_id", sa.String(128), nullable=True),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "listening_pool",
        sa.Column("spotify_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("artist", sa.String(512), nullable=False),
        sa.Column("album", sa.String(512), nullable=True),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("availability", sa.String(16), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=True),
        sa.Column("song_id", sa.String(64), nullable=True),
        sa.Column("tab_id", sa.String(64), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_listening_pool_score", "listening_pool", ["score"])
    op.create_index("ix_listening_pool_status", "listening_pool", ["status"])


def downgrade() -> None:
    op.drop_index("ix_listening_pool_status", table_name="listening_pool")
    op.drop_index("ix_listening_pool_score", table_name="listening_pool")
    op.drop_table("listening_pool")
    op.drop_table("spotify_auth")
