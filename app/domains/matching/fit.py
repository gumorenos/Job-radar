from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import WorkMode
from app.domains.jobs.normalization import comparison_key

_ROLE_EQUIVALENTS = (
    "hrbp",
    "hr business partner",
    "human resources business partner",
    "analista senior",
    "especialista senior",
    "coordinador",
    "coordinator",
    "supervisor",
    "jefe",
    "lead",
    "manager",
    "gerente",
)
_CORE_AREA_EQUIVALENTS = (
    "onboarding",
    "people analytics",
    "gestion humana",
    "compensaciones",
    "compensation",
    "relaciones laborales",
    "rrll",
    "hr analytics",
    "recursos humanos",
    "human resources",
    "capital humano",
    "gestion de personas",
)
_ADJACENT_AREA_EQUIVALENTS = (
    "people operations",
    "hr operations",
    "talent management",
    "organizational development",
    "desarrollo organizacional",
    "workforce analytics",
    "hr transformation",
    "employee experience",
    "total rewards",
    "hris",
    "hr systems",
)


@dataclass(frozen=True)
class FitSignalInput:
    title: str | None
    description: str | None
    location: str | None
    work_mode: WorkMode
    monthly_salary_pen: Decimal | None
    target_roles: tuple[str, ...]
    target_areas: tuple[str, ...]
    adjacent_areas: tuple[str, ...]


@dataclass(frozen=True)
class FitEvaluation:
    role_matches: tuple[str, ...]
    core_area_matches: tuple[str, ...]
    adjacent_area_matches: tuple[str, ...]
    high_priority: bool
    strengths: tuple[str, ...]
    gaps: tuple[str, ...]


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _role_match(term: str, title_key: str) -> bool:
    term_key = comparison_key(term)
    if not term_key or not title_key:
        return False
    title_tokens = set(title_key.split())
    term_tokens = set(term_key.split())
    return bool(term_tokens) and term_tokens.issubset(title_tokens)


def _phrase_matches(terms: tuple[str, ...], text_key: str) -> list[str]:
    matches: list[str] = []
    words = set(text_key.split())
    for term in terms:
        term_key = comparison_key(term)
        if not term_key:
            continue
        matched = term_key in text_key if " " in term_key else term_key in words
        if matched:
            matches.append(term)
    return matches


def evaluate_positive_fit(facts: FitSignalInput) -> FitEvaluation:
    title_key = comparison_key(facts.title) or ""
    text_key = comparison_key(" ".join(filter(None, (facts.title, facts.description)))) or ""

    role_terms = _dedupe([*facts.target_roles, *_ROLE_EQUIVALENTS])
    core_terms = _dedupe([*facts.target_areas, *_CORE_AREA_EQUIVALENTS])
    adjacent_terms = _dedupe([*facts.adjacent_areas, *_ADJACENT_AREA_EQUIVALENTS])

    role_matches = _dedupe([term for term in role_terms if _role_match(term, title_key)])
    core_matches = _dedupe(_phrase_matches(core_terms, text_key))
    adjacent_matches = _dedupe(_phrase_matches(adjacent_terms, text_key))

    strengths: list[str] = []
    gaps: list[str] = []

    if role_matches:
        strengths.append(f"Rol objetivo detectado: {role_matches[0]}.")
    else:
        gaps.append("El título no confirma todavía un rol objetivo de Job Radar.")

    if core_matches:
        strengths.append(f"Área foco detectada: {core_matches[0]}.")
    elif adjacent_matches:
        strengths.append(f"Área adyacente detectada: {adjacent_matches[0]}.")
        gaps.append("El encaje es adyacente; conviene revisar el alcance real del puesto.")
    else:
        gaps.append("No se detectó una de las áreas foco en el título o descripción.")

    if facts.monthly_salary_pen is not None:
        strengths.append("El salario publicado superó las reglas mínimas de descarte.")
    else:
        gaps.append("El salario no está publicado; no impide priorizar, pero queda como incógnita.")

    location_key = comparison_key(facts.location) or ""
    if facts.work_mode == WorkMode.REMOTE:
        strengths.append("La modalidad remota es compatible con la búsqueda.")
    elif "lima" in location_key:
        strengths.append("La ubicación está dentro de Lima.")

    high_priority = bool(role_matches and core_matches)
    return FitEvaluation(
        role_matches=role_matches,
        core_area_matches=core_matches,
        adjacent_area_matches=adjacent_matches,
        high_priority=high_priority,
        strengths=tuple(strengths),
        gaps=tuple(gaps),
    )
