"""
pass Culture – Statut d'éligibilité par âge et date
=======================================================

Détermine quel statut d'éligibilité *pass Culture* s'applique à une
personne, selon sa date de naissance, la date d'évaluation et — pour les
résidents d'outre-mer — son département (anniversaire à minuit local, pas
à Paris). Voir ``metadata.json`` pour les références légales complètes.


Reconstruit et recoupé (sans copie) avec
``pcapi.core.users.eligibility_api.get_eligibility_at_date`` et les
fonctions voisines de ce module.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from regalgo import AlgoInput, AlgoResult

from pass_culture_rules._base import BaseRule

# Miroir de pcapi.utils.date.CUSTOM_TIMEZONES — code département -> fuseau IANA.
_CUSTOM_TIMEZONES: dict[str, str] = {
    "971": "America/Guadeloupe", "972": "America/Martinique", "973": "America/Cayenne",
    "974": "Indian/Reunion", "975": "America/Miquelon", "976": "Indian/Mayotte",
    "977": "America/St_Barthelemy", "978": "America/Guadeloupe", "986": "Pacific/Wallis",
    "987": "Pacific/Tahiti", "988": "Pacific/Noumea", "989": "Pacific/Pitcairn",
}
_METROPOLE_TIMEZONE = "Europe/Paris"


def _department_timezone(department_code: Optional[str]) -> str:
    return _METROPOLE_TIMEZONE if department_code is None else _CUSTOM_TIMEZONES.get(department_code, _METROPOLE_TIMEZONE)


def _add_years(d: datetime.date, years: int) -> datetime.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, month=2, day=28)


def _department_midnight(d: datetime.date, department_code: Optional[str]) -> datetime.datetime:
    return datetime.datetime.combine(d, datetime.time.min, tzinfo=ZoneInfo(_department_timezone(department_code)))


def _to_department_tz(at_datetime: datetime.datetime, department_code: Optional[str]) -> datetime.datetime:
    if at_datetime.tzinfo is None:
        at_datetime = at_datetime.replace(tzinfo=datetime.timezone.utc)
    return at_datetime.astimezone(ZoneInfo(_department_timezone(department_code)))


def _parse_date(value: Any) -> Optional[datetime.date]:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value.date() if isinstance(value, datetime.datetime) else value
    return datetime.date.fromisoformat(value)


def _parse_datetime(value: Any) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(value)


class StatutEligibiliteAlgo(BaseRule):
    """Statut d'éligibilité par âge/date/département (Décret 2021-628, Décret 2025-195)."""

    def __init__(self) -> None:
        super().__init__(Path(__file__).parent)

    def compute(self, algo_input: AlgoInput) -> AlgoResult:

        data = algo_input.data
        context = algo_input.context

        birth_date = _parse_date(data.get("date_naissance"))
        department_code = _parse_date(data.get('department'))
        at_datetime = _parse_datetime(context["date_evaluation"])
        credit_v3_decree_datetime = _parse_datetime(context["date_decret_v3"])

        if birth_date is None:
            return self._result("not_eligible", data, {"raison": "date_naissance_inconnue"})

        start = _department_midnight(_add_years(birth_date, 15), department_code)
        end = _department_midnight(_add_years(birth_date, 19), department_code)
        at_tz_aware = at_datetime if at_datetime.tzinfo else at_datetime.replace(tzinfo=datetime.timezone.utc)
        if not (start <= at_tz_aware < end):
            return self._result("not_eligible", data, {"raison": "hors_fenetre_15_19_ans"})

        localized_now = _to_department_tz(at_datetime, department_code)
        localized_birth = _department_midnight(birth_date, department_code)
        age = localized_now.year - localized_birth.year
        if (localized_now.month, localized_now.day) < (localized_birth.month, localized_birth.day):
            age -= 1
        age = max(0, age)

        statut: Optional[str] = None
        if at_datetime < credit_v3_decree_datetime:
            if age in (15, 16, 17):
                statut = "underage"
            elif age == 18:
                statut = "age18"

        if statut is None:
            if 17 <= age <= 18:
                statut = "age17_18"
            elif 15 <= age <= 16:
                statut = "free"

        if statut is None:
            statut = 'not_eligible'
        return self._result(
            statut,
            data,
            {
                "age": age,
                "is_underage": statut == "underage" or (statut == "age17_18" and age < 18),
                "is_18_or_above": statut == "age18" or (statut == "age17_18" and age >= 18),
            },
        )

    def _result(self, value: Optional[str], data: dict[str, Any], metadata: dict[str, Any]) -> AlgoResult:
        if value != 'not_eligible':
            metadata['redirect_url'] = "https://passculture.app/creation-compte?from=data.gouv"
        return AlgoResult(
            value=value,
            algo_id=self.algo_id,
            regulation=self.regulation,
            inputs_snapshot=data,
            metadata=metadata
        )
