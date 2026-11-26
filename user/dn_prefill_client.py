import httpx


class DemarchePrefillError(Exception):
    """Démarche numérique (DS) prefill HTTP call failed."""


async def create_prefilled_dossier(config: dict, demarche_id: str, prefill_body: dict) -> dict:
    """Create a pre-filled draft dossier via the Demarches Numériques public
    prefill API (no authentication).

    POST /api/public/v1/demarches/<id>/dossiers with the champ keys/values as
    JSON; the response contains ``dossier_url`` to send the user to. Dossier
    is created as an orphan draft and attached to the user after they sign in.
    https://doc.demarches-simplifiees.fr/pour-aller-plus-loin/api-de-preremplissage
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{config['base_url']}/api/public/v1/demarches/{demarche_id}/dossiers",
            json=prefill_body,
        )
    if resp.status_code != 201:
        raise DemarchePrefillError(
            f"demarche prefill failed: {resp.status_code} {resp.text}"
        )
    return resp.json()
