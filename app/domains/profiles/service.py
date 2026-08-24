from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateProfile


def get_or_create_active_profile(session: Session) -> CandidateProfile:
    profile = session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.created_at.asc())
        .limit(1)
    )
    if profile is not None:
        return profile

    profile = CandidateProfile(
        name="Perfil personal",
        is_active=True,
        salary_min_pen=Decimal("7000"),
        remote_salary_multiplier=Decimal("1.10"),
        experience_years=Decimal("5"),
        degrees=[],
        skills=[],
        transferable_skills=[],
        target_locations=["Lima Metropolitana", "Remote LATAM", "Remote Global"],
        target_roles=[
            "Senior Analyst",
            "Senior Specialist",
            "Coordinator",
            "Supervisor",
            "HR Business Partner",
            "Senior HRBP",
            "Strategic HRBP",
            "Jefe",
            "Lead",
            "Manager",
            "Gerente",
        ],
        target_areas=[
            "Onboarding",
            "People Analytics",
            "Gestión Humana",
            "Compensaciones",
            "Relaciones Laborales",
            "HR Analytics",
            "Recursos Humanos",
            "Capital Humano",
            "Gestión de Personas",
        ],
        adjacent_areas=[
            "People Operations",
            "HR Operations",
            "Talent Management",
            "Organizational Development",
            "Workforce Analytics",
            "HR Transformation",
            "Employee Experience",
            "Total Rewards",
            "HRIS",
            "HR Systems",
        ],
        rules={"source": "phase-0-confirmed-rules"},
    )
    session.add(profile)
    session.flush()
    return profile
