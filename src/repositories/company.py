"""
Репозиторий компаний v2.

Добавлен метод get_pending_with_details — JOIN компании + верификации + владелец
для панели куратора. Всё в одном запросе, без N+1.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import RepositoryError
from src.models.company import Company, CompanyVerification
from src.models.enums import VerificationStatus
from src.models.user import User
from src.repositories.base import BaseRepository
from src.schemas.company import (
    CompanyRegisterRequest,
    CompanyVerificationDetailResponse,
    InnLookupResult,
)

logger = structlog.get_logger()


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def get_by_inn(self, inn: str) -> Company | None:
        try:
            result = await self.db.execute(select(Company).where(Company.inn == inn))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("DB error get_by_inn", error=str(e))
            raise RepositoryError() from e

    async def get_by_owner(self, owner_id: UUID) -> Company | None:
        try:
            result = await self.db.execute(select(Company).where(Company.owner_id == owner_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_latest_verification(self, company_id: UUID) -> CompanyVerification | None:
        try:
            result = await self.db.execute(
                select(CompanyVerification)
                .where(CompanyVerification.company_id == company_id)
                .order_by(CompanyVerification.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def create_with_verification(
        self,
        owner_id: UUID,
        dadata_result: InnLookupResult,
        request: CompanyRegisterRequest,
        email_domain_verified: bool,
    ) -> tuple[Company, CompanyVerification]:
        try:
            company = Company(
                owner_id=owner_id,
                name=dadata_result.short_name,
                legal_name=dadata_result.full_name,
                inn=dadata_result.inn,
                city=dadata_result.city,
                description=request.description,
                short_description=request.short_description,
                industry=request.industry,
                company_size=request.company_size,
                website_url=request.website_url,
                corporate_email=request.corporate_email,
                verification_status=VerificationStatus.PENDING,
                is_active=True,
            )
            self.db.add(company)
            await self.db.flush()

            verification = CompanyVerification(
                company_id=company.id,
                status=VerificationStatus.PENDING,
                inn=dadata_result.inn,
                inn_verified=True,
                corporate_email=request.corporate_email,
                email_domain_verified=email_domain_verified,
                verification_links=request.verification_links,
            )
            self.db.add(verification)
            await self.db.commit()
            await self.db.refresh(company)
            await self.db.refresh(verification)
            return company, verification

        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError() from e

    async def get_pending_with_details(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyVerificationDetailResponse]:
        """
        JOIN: Company + CompanyVerification + User(owner).
        Один SQL-запрос — без N+1 проблемы.
        Куратор получает всё нужное в одном ответе.
        """
        try:
            stmt = (
                select(Company, CompanyVerification, User)
                .join(
                    CompanyVerification,
                    CompanyVerification.company_id == Company.id,
                )
                .join(User, User.id == Company.owner_id)
                .where(Company.verification_status == VerificationStatus.PENDING)
                .order_by(CompanyVerification.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            rows = result.all()

            return [
                CompanyVerificationDetailResponse(
                    company_id=company.id,
                    company_name=company.name,
                    legal_name=company.legal_name,
                    inn=verification.inn,
                    inn_verified=verification.inn_verified,
                    ogrn=None,
                    owner_email=owner.email,
                    corporate_email=verification.corporate_email,
                    email_domain_verified=verification.email_domain_verified,
                    website_url=company.website_url,
                    city=company.city,
                    industry=company.industry,
                    company_size=company.company_size,
                    description=company.description,
                    verification_links=verification.verification_links or [],
                    documents=verification.documents or [],
                    verification_status=company.verification_status,
                    curator_comment=verification.curator_comment,
                    submitted_at=verification.created_at,
                )
                for company, verification, owner in rows
            ]
        except SQLAlchemyError as e:
            logger.error("DB error get_pending_with_details", error=str(e))
            raise RepositoryError() from e
