"""add_inn_dadata_fields

Revision ID: a1b2c3d4e5f6
Revises: 41aa86a76f51
Create Date: 2026-03-23 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "41aa86a76f51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Добавляем поле inn_dadata_verified_at в companies
    и расширяем company_verifications полями okved, ogrn, registration_date, ceo_name.
    """
    # Добавляем в companies: дата когда ИНН был верифицирован через Dadata
    op.add_column(
        "companies",
        sa.Column("inn_dadata_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Краткое наименование из Dadata (удобно для отображения)
    op.add_column(
        "companies",
        sa.Column("inn_short_name", sa.Text, nullable=True),
    )

    # Расширяем company_verifications
    op.add_column(
        "company_verifications",
        sa.Column("okved", sa.Text, nullable=True),
    )
    op.add_column(
        "company_verifications",
        sa.Column("ogrn", sa.Text, nullable=True),
    )
    op.add_column(
        "company_verifications",
        sa.Column(
            "registration_date",
            sa.BigInteger,  # Unix timestamp из Dadata
            nullable=True,
        ),
    )
    op.add_column(
        "company_verifications",
        sa.Column("ceo_name", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Откат изменений."""
    op.drop_column("company_verifications", "ceo_name")
    op.drop_column("company_verifications", "registration_date")
    op.drop_column("company_verifications", "ogrn")
    op.drop_column("company_verifications", "okved")
    op.drop_column("companies", "inn_short_name")
    op.drop_column("companies", "inn_dadata_verified_at")
