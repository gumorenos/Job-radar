from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import WorkMode
from app.domains.jobs.normalization import comparison_key

_ROLE_EQUIVALENTS = (
    "hrbp",
    "hr business partner",
    "human resources business partner",
    "strategic hrbp",
    "analista senior",
    "senior analyst",
    "especialista senior",
    "senior specialist",
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
_GENERIC_ROLE_KEYS = {
    "analista senior",
    "senior analyst",
    "especialista senior",
    "senior specialist",
    "coordinador",
    "coordinator",
    "supervisor",
    "jefe",
    "lead",
    "manager",
    "gerente",
}
_HR_TITLE_CONTEXT = (
    "hr",
    "human resources",
    "recursos humanos",
    "people",
    "gestion humana",
    "capital humano",
    "gestion de personas",
    "talent",
    "compensation",
    "compensaciones",
    "relaciones laborales",
    "rrll",
    "onboarding",
    "employee",
    "workforce",
    "total rewards",
    "hris",
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


def _contains_phrase(text_key: str, term: str) -> bool:
    term_key = comparison_key(term)
    if not term_key:
        return False
    if " " in term_key:
        return term_key in text_key
    return term_key in set(text_key.split())


def _has_hr_title_context(title_key: str) -> bool:
    return any(_contains_phrase(title_key, term) for term in _HR_TITLE_CONTEXT)


def _role_match(term: str, title_key: str) -> bool:
    term_key = comparison_key(term)
    if not term_key or not title_key:
        return False
    title_tokens = set(title_key.split())
    term_tokens = set(term_key.split())
    matched = bool(term_tokens) and term_tokens.issubset(title_tokens)
    if not matched:
        return False

    # Seniority-only titles are too generic by themselves. Requiring HR/People context in
    # the title prevents e.g. "Operations Manager" from being promoted because the body
    # happens to mention an HR initiative.
    return term_key not in _GENERIC_ROLE_KEYS or _has_hr_title_context(title_key)


def _phrase_matches(terms: tuple[str, ...], text_key: str) -> list[str]:
    return [term for term in terms if _contains_phrase(text_key, term)]


def assess_career_move(fit: FitEvaluation) -> str:
    """Describe strategic alignment without inventing candidate-history facts."""
    if fit.role_matches and fit.core_area_matches:
        return (
            "Movimiento alineado: combina un rol objetivo con un área foco de la búsqueda. "
            "La progresión concreta depende del alcance y responsabilidades del puesto."
        )
    if fit.role_matches and fit.adjacent_area_matches:
        return (
            "Movimiento adyacente: el rol está dentro del objetivo, pero el contenido visible "
            "se concentra en un área adyacente; conviene revisar alcance y exposición estratégica."
        )
    if fit.role_matches:
        return (
            "Rol alineado con alcance por confirmar: el título encaja con la búsqueda, pero la "
            "descripción no confirma todavía un área foco o adyacente."
        )
    if fit.core_area_matches:
        return (
            "Área alineada con nivel por confirmar: el contenido toca un área foco, pero el título "
            "no confirma un rol objetivo de RRHH/People."
        )
    if fit.adjacent_area_matches:
        return (
            "Movimiento exploratorio: aparece un área adyacente, sin evidencia suficiente de rol "
            "objetivo ni de área foco."
        )
    return (
        "Movimiento no confirmado: con la información disponible no se observa todavía una "
        "alineación clara con rol objetivo o áreas priorizadas."
    )


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
        gaps.append("El título no confirma todavía un rol objetivo de RRHH/People para Job Radar.")

    if core_matches:
        strengths.append(f"Área foco detectada: {core_matches[0]}.")
    elif adjacent_matches:
        strengths.append(f"Área adyacente detectada: {adjacent_matches[0]}.")
        gaps.append("El encaje es adyacente; conviene revisar el alcance real del puesto.")
    else:
        gaps.append("No se detectó una de las áreas foco en el título o descripción.")

    if facts.monthly_salary_pen is not None:
        strengths.append("Hay salario publicado y normalizado a PEN mensual.")
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
