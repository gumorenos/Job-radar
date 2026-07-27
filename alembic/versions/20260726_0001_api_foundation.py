"""Baseline legacy tables and API ingestion runs.

Revision ID: 20260726_0001
Revises:
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

from job_radar_app import models  # noqa: F401
from job_radar_app.database import Base


revision = "20260726_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safe for the existing SQLite MVP: create_all only adds missing tables and indexes.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # The baseline intentionally preserves legacy radar data. Only remove the new API table.
    bind = op.get_bind()
    if "ingestion_runs" in inspect(bind).get_table_names():
        op.drop_table("ingestion_runs")
