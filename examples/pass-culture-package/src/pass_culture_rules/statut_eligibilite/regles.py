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
import re
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

# Démarche numérique de redirection : « Pass Culture (test DINUM) », n° 162223,
# en brouillon (slug UUID, accessible avec ?test=true). Le pré-remplissage
# passe par l'API publique de préremplissage POST
# /api/public/v1/demarches/<id>/dossiers — la réponse contient ``dossier_url``
# vers laquelle diriger l'usager. Clés de champ stables (base 64) relevées
# sur la page /preremplir/<slug> de la démarche :
# https://doc.demarches-simplifiees.fr/pour-aller-plus-loin/api-de-preremplissage
_DEMARCHE_NUMERIQUE_URL = (
    "https://demarche.numerique.gouv.fr/commencer/"
    "009cbfb4-f492-47d5-932f-2a437bdca3b6?test=true"
)
_DEMARCHE_NUMERIQUE_ID = "162223"
_CHAMP_DATE_NAISSANCE = "champ_Q2hhbXAtNzI0NzcyNg"
_CHAMP_DEPARTEMENT = "champ_Q2hhbXAtNzI0NzczMQ"


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


def _departement_depuis_adresse(address: Any) -> Optional[str]:
    """Département résidentiel déduit de l'adresse API Particulier.

    ``address.code_postal_ville`` (CAF) a la forme « 63100 CLERMONT
    FERRAND » : le numéro de département se déduit du préfixe du code
    postal — 2 chiffres en métropole, 3 pour les DROM (97x/98x). Les
    codes corses (20xxx) couvrent à la fois la Corse-du-Sud (2A) et la
    Haute-Corse (2B) : sans la commune, le département est indécidable
    et le champ n'est pas pré-rempli (l'usager le saisit).
    """
    if not isinstance(address, dict):
        return None
    code_postal_ville = address.get("code_postal_ville")
    if not isinstance(code_postal_ville, str):
        return None
    match = re.match(r"\s*(\d{2,3})", code_postal_ville)
    if match is None:
        return None
    prefix = match.group(1)
    if prefix.startswith(("97", "98")):
        return prefix
    if prefix[:2] == "20":
        return None
    return prefix[:2]


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
            prefill_body = {_CHAMP_DATE_NAISSANCE: data.get("date_naissance")}
            departement = _departement_depuis_adresse(data.get("address"))
            if departement is not None:
                prefill_body[_CHAMP_DEPARTEMENT] = departement
            metadata['demarche_prefill'] = {
                "demarche_id": _DEMARCHE_NUMERIQUE_ID,
                "prefill_body": prefill_body,
            }
            # Repli sans pré-remplissage si l'appel POST échoue côté front.
            metadata['redirect_url'] = _DEMARCHE_NUMERIQUE_URL
        return AlgoResult(
            value=value,
            algo_id=self.algo_id,
            regulation=self.regulation,
            inputs_snapshot=data,
            metadata=metadata
        )
