from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import Classification, WorkMode
from app.domains.jobs.normalization import comparison_key

_DISALLOWED_TITLE_TERMS = (
    "practicante",
    "practicas",
    "intern",
    "internship",
    "asistente",
    "assistant",
    "junior",
    "jr",
)
_AGRICULTURE_TERMS = (
    "agricola",
    "agricultura",
    "agro",
    "agroindustrial",
    "agroindustria",
)
# Lima Province plus Callao, which is treated as part of the user's valid Lima
# metropolitan search area. All values are comparison-key normalized (ASCII/lowercase).
_LIMA_TERMS = (
    "lima",
    "cercado de lima",
    "ancon",
    "ate",
    "barranco",
    "brena",
    "carabayllo",
    "chaclacayo",
    "chorrillos",
    "cieneguilla",
    "comas",
    "el agustino",
    "independencia",
    "jesus maria",
    "la molina",
    "la victoria",
    "lince",
    "los olivos",
    "lurigancho",
    "chosica",
    "lurigancho chosica",
    "lurin",
    "magdalena",
    "magdalena del mar",
    "miraflores",
    "pachacamac",
    "pucusana",
    "pueblo libre",
    "puente piedra",
    "punta hermosa",
    "punta negra",
    "rimac",
    "san bartolo",
    "san borja",
    "san isidro",
    "san juan de lurigancho",
    "san juan de miraflores",
    "san luis",
    "san martin de porres",
    "san miguel",
    "santa anita",
    "santa maria del mar",
    "santa rosa",
    "santiago de surco",
    "surco",
    "surquillo",
    "villa el salvador",
    "villa maria del triunfo",
    "callao",
    "bellavista",
    "carmen de la legua",
    "carmen de la legua reynoso",
    "la perla",
    "la punta",
    "mi peru",
    "ventanilla",
)


@dataclass(frozen=True)
class MatchingRuleInput:
    title: str | None
    location: str | None
    work_mode: WorkMode
    industry: str | None = None
    monthly_salary_pen: Decimal | None = None
    is_international_remote: bool = False
    degree_mismatch: bool = False
    degree_is_required: bool = False
    requested_years_experience: int | None = None
    candidate_years_experience: int | None = None


@dataclass(frozen=True)
class MatchingRulePolicy:
    local_salary_min_pen: Decimal = Decimal("7000")
    remote_salary_min_pen: Decimal = Decimal("7700")


@dataclass(frozen=True)
class RuleResult:
    code: str
    passed: bool
    severity: str
    message: str


@dataclass(frozen=True)
class RuleEvaluation:
    forced_classification: Classification | None
    requires_review: bool
    results: tuple[RuleResult, ...]


def _contains(text: str | None, terms: tuple[str, ...]) -> bool:
    key = comparison_key(text)
    if not key:
        return False
    words = set(key.split())
    return any(term in key if " " in term else term in words for term in terms)


def _is_lima_metropolitana(location: str | None) -> bool:
    return _contains(location, _LIMA_TERMS)


def evaluate_business_rules(
    facts: MatchingRuleInput,
    policy: MatchingRulePolicy | None = None,
) -> RuleEvaluation:
    policy = policy or MatchingRulePolicy()
    results: list[RuleResult] = []
    hard_discard = False
    requires_review = False

    excluded_title = _contains(facts.title, _DISALLOWED_TITLE_TERMS)
    results.append(
        RuleResult(
            code="SENIORITY_TITLE",
            passed=not excluded_title,
            severity="HARD" if excluded_title else "INFO",
            message=(
                "El título corresponde a prácticas, asistente o junior."
                if excluded_title
                else "El título no activa un descarte por seniority."
            ),
        )
    )
    hard_discard = hard_discard or excluded_title

    onsite_outside_lima = (
        facts.work_mode == WorkMode.ONSITE
        and bool(comparison_key(facts.location))
        and not _is_lima_metropolitana(facts.location)
    )
    results.append(
        RuleResult(
            code="ONSITE_LOCATION",
            passed=not onsite_outside_lima,
            severity="HARD" if onsite_outside_lima else "INFO",
            message=(
                "La vacante es 100% presencial fuera de Lima Metropolitana."
                if onsite_outside_lima
                else "La ubicación/modalidad no activa descarte geográfico."
            ),
        )
    )
    hard_discard = hard_discard or onsite_outside_lima

    salary_floor = (
        policy.remote_salary_min_pen
        if facts.is_international_remote
        else policy.local_salary_min_pen
    )
    salary_too_low = (
        facts.monthly_salary_pen is not None and facts.monthly_salary_pen < salary_floor
    )
    results.append(
        RuleResult(
            code="PUBLISHED_SALARY",
            passed=not salary_too_low,
            severity="HARD" if salary_too_low else "INFO",
            message=(
                f"El salario publicado está por debajo de S/{salary_floor:,.0f} mensuales."
                if salary_too_low
                else (
                    "El salario no fue publicado; no se descarta."
                    if facts.monthly_salary_pen is None
                    else "El salario publicado cumple el mínimo aplicable."
                )
            ),
        )
    )
    hard_discard = hard_discard or salary_too_low

    agriculture = _contains(facts.industry, _AGRICULTURE_TERMS)
    if agriculture:
        requires_review = True
    results.append(
        RuleResult(
            code="AGRICULTURE_INDUSTRY",
            passed=not agriculture,
            severity="WARNING" if agriculture else "INFO",
            message=(
                "Industria agrícola/agroindustrial: enviar a revisión, no descartar."
                if agriculture
                else "La industria no activa revisión especial."
            ),
        )
    )

    degree_warning = facts.degree_mismatch and facts.degree_is_required
    if degree_warning:
        requires_review = True
    results.append(
        RuleResult(
            code="DEGREE_MISMATCH",
            passed=not degree_warning,
            severity="WARNING" if degree_warning else "INFO",
            message=(
                "El grado requerido no coincide; revisar manualmente antes de decidir."
                if degree_warning
                else "No hay una brecha de grado excluyente identificada."
            ),
        )
    )

    experience_gap = (
        facts.requested_years_experience is not None
        and facts.candidate_years_experience is not None
        and facts.requested_years_experience > facts.candidate_years_experience
    )
    if experience_gap:
        requires_review = True
    results.append(
        RuleResult(
            code="EXPERIENCE_GAP",
            passed=not experience_gap,
            severity="WARNING" if experience_gap else "INFO",
            message=(
                "Hay una brecha de años de experiencia; se advierte pero no se descarta."
                if experience_gap
                else "No se identificó brecha de años de experiencia."
            ),
        )
    )

    return RuleEvaluation(
        forced_classification=Classification.DISCARD if hard_discard else None,
        requires_review=requires_review,
        results=tuple(results),
    )
