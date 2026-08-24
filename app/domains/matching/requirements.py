from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domains.jobs.normalization import comparison_key


class RequirementStatus(StrEnum):
    MEETS = "MEETS"
    PARTIALLY = "PARTIALLY"
    TRANSFERABLE = "TRANSFERABLE"
    DOES_NOT_MEET = "DOES_NOT_MEET"
    POSSIBLE_EXCLUSION = "POSSIBLE_EXCLUSION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RequirementAssessment:
    status: RequirementStatus
    message: str
    requires_review: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "message": self.message,
            "requires_review": self.requires_review,
        }


@dataclass(frozen=True)
class SkillRequirementAssessment:
    skill: str
    status: RequirementStatus
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "skill": self.skill,
            "status": self.status.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class StructuredFitAssessment:
    experience: RequirementAssessment
    degree: RequirementAssessment
    skills: RequirementAssessment
    skill_items: tuple[SkillRequirementAssessment, ...]

    @property
    def requires_review(self) -> bool:
        return any(
            item.requires_review
            for item in (self.experience, self.degree, self.skills)
        )

    @property
    def strengths(self) -> tuple[str, ...]:
        strengths: list[str] = []
        for item in (self.experience, self.degree, self.skills):
            if item.status in (RequirementStatus.MEETS, RequirementStatus.TRANSFERABLE):
                strengths.append(item.message)
        return tuple(strengths)

    @property
    def gaps(self) -> tuple[str, ...]:
        gaps: list[str] = []
        for item in (self.experience, self.degree, self.skills):
            if item.status in (
                RequirementStatus.PARTIALLY,
                RequirementStatus.DOES_NOT_MEET,
                RequirementStatus.POSSIBLE_EXCLUSION,
            ):
                gaps.append(item.message)
        return tuple(gaps)

    def as_dict(self) -> dict[str, object]:
        return {
            "experience": self.experience.as_dict(),
            "degree": self.degree.as_dict(),
            "skills": self.skills.as_dict(),
            "skill_items": [item.as_dict() for item in self.skill_items],
            "requires_review": self.requires_review,
        }


def _keys(values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for value in values:
        key = comparison_key(value)
        if key:
            normalized.append((value, key))
    return tuple(normalized)


def _matches(candidate_key: str, requirement_key: str) -> bool:
    if candidate_key == requirement_key:
        return True
    if len(candidate_key) >= 4 and candidate_key in requirement_key:
        return True
    if len(requirement_key) >= 4 and requirement_key in candidate_key:
        return True
    candidate_tokens = set(candidate_key.split())
    requirement_tokens = set(requirement_key.split())
    return bool(candidate_tokens and requirement_tokens) and (
        candidate_tokens.issubset(requirement_tokens)
        or requirement_tokens.issubset(candidate_tokens)
    )


def assess_experience(
    candidate_years: Decimal | None,
    required_years: Decimal | None,
) -> RequirementAssessment:
    if required_years is None:
        return RequirementAssessment(
            RequirementStatus.UNKNOWN,
            "La vacante no publica un mínimo estructurado de experiencia.",
        )
    if candidate_years is None:
        return RequirementAssessment(
            RequirementStatus.UNKNOWN,
            f"La vacante pide {required_years:g} años; falta registrar la experiencia del perfil.",
        )
    if candidate_years >= required_years:
        return RequirementAssessment(
            RequirementStatus.MEETS,
            f"Experiencia: cumple {candidate_years:g} años frente a {required_years:g} requeridos.",
        )

    gap = required_years - candidate_years
    if gap <= Decimal("2"):
        return RequirementAssessment(
            RequirementStatus.PARTIALLY,
            f"Experiencia: {candidate_years:g} años frente a {required_years:g} requeridos; brecha de {gap:g} años.",
            requires_review=True,
        )
    return RequirementAssessment(
        RequirementStatus.DOES_NOT_MEET,
        f"Experiencia: {candidate_years:g} años frente a {required_years:g} requeridos; brecha de {gap:g} años.",
        requires_review=True,
    )


def assess_degree(
    candidate_degrees: tuple[str, ...],
    required_degrees: tuple[str, ...],
) -> RequirementAssessment:
    required = _keys(required_degrees)
    if not required:
        return RequirementAssessment(
            RequirementStatus.UNKNOWN,
            "La vacante no registra un grado o carrera requerida.",
        )
    candidates = _keys(candidate_degrees)
    if not candidates:
        return RequirementAssessment(
            RequirementStatus.UNKNOWN,
            "La vacante publica un requisito de carrera, pero el perfil aún no tiene grados registrados.",
        )

    for candidate_label, candidate_key in candidates:
        for required_label, required_key in required:
            if _matches(candidate_key, required_key):
                return RequirementAssessment(
                    RequirementStatus.MEETS,
                    f"Carrera/grado: {candidate_label} es compatible con {required_label}.",
                )

    requested = ", ".join(label for label, _ in required[:3])
    return RequirementAssessment(
        RequirementStatus.POSSIBLE_EXCLUSION,
        f"Carrera/grado: no se observa coincidencia directa con el requisito publicado ({requested}).",
        requires_review=True,
    )


def _skill_item(
    skill: str,
    direct: tuple[tuple[str, str], ...],
    transferable: tuple[tuple[str, str], ...],
) -> SkillRequirementAssessment:
    requirement_key = comparison_key(skill) or ""
    for candidate_label, candidate_key in direct:
        if _matches(candidate_key, requirement_key):
            return SkillRequirementAssessment(
                skill,
                RequirementStatus.MEETS,
                f"Skill requerido cubierto por {candidate_label}.",
            )
    for candidate_label, candidate_key in transferable:
        if _matches(candidate_key, requirement_key):
            return SkillRequirementAssessment(
                skill,
                RequirementStatus.TRANSFERABLE,
                f"Skill {skill} cubierto como transferible mediante {candidate_label}.",
            )
    return SkillRequirementAssessment(
        skill,
        RequirementStatus.DOES_NOT_MEET,
        f"No se observa evidencia registrada para el skill requerido {skill}.",
    )


def assess_skills(
    candidate_skills: tuple[str, ...],
    transferable_skills: tuple[str, ...],
    required_skills: tuple[str, ...],
) -> tuple[RequirementAssessment, tuple[SkillRequirementAssessment, ...]]:
    required = tuple(item for item in required_skills if comparison_key(item))
    if not required:
        return (
            RequirementAssessment(
                RequirementStatus.UNKNOWN,
                "La vacante no registra skills obligatorios estructurados.",
            ),
            (),
        )
    if not candidate_skills and not transferable_skills:
        return (
            RequirementAssessment(
                RequirementStatus.UNKNOWN,
                "La vacante publica skills requeridos, pero el perfil aún no tiene skills registrados.",
            ),
            (),
        )

    direct = _keys(candidate_skills)
    transferable = _keys(transferable_skills)
    items = tuple(_skill_item(skill, direct, transferable) for skill in required)
    statuses = {item.status for item in items}

    if statuses == {RequirementStatus.MEETS}:
        assessment = RequirementAssessment(
            RequirementStatus.MEETS,
            "Skills: cumple todos los requisitos estructurados publicados.",
        )
    elif statuses.issubset({RequirementStatus.MEETS, RequirementStatus.TRANSFERABLE}):
        assessment = RequirementAssessment(
            RequirementStatus.TRANSFERABLE,
            "Skills: los requisitos están cubiertos entre evidencia directa y capacidades transferibles.",
        )
    elif RequirementStatus.MEETS in statuses or RequirementStatus.TRANSFERABLE in statuses:
        assessment = RequirementAssessment(
            RequirementStatus.PARTIALLY,
            "Skills: cumple parte de los requisitos publicados; quedan brechas por revisar.",
            requires_review=True,
        )
    else:
        assessment = RequirementAssessment(
            RequirementStatus.DOES_NOT_MEET,
            "Skills: no se observa evidencia registrada para los requisitos publicados.",
            requires_review=True,
        )
    return assessment, items


def assess_structured_fit(
    *,
    candidate_experience_years: Decimal | None,
    candidate_degrees: tuple[str, ...],
    candidate_skills: tuple[str, ...],
    transferable_skills: tuple[str, ...],
    required_experience_years: Decimal | None,
    required_degrees: tuple[str, ...],
    required_skills: tuple[str, ...],
) -> StructuredFitAssessment:
    skills, skill_items = assess_skills(
        candidate_skills,
        transferable_skills,
        required_skills,
    )
    return StructuredFitAssessment(
        experience=assess_experience(candidate_experience_years, required_experience_years),
        degree=assess_degree(candidate_degrees, required_degrees),
        skills=skills,
        skill_items=skill_items,
    )
