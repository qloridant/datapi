import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import server

MANIFEST = json.loads((Path(__file__).parent.parent / "examples/civique-droit-vote/manifest.json").read_text())
ELIGIBLE = {"data": {"nationalite_francaise": True, "age": 30, "capacite_civique": True, "inscrit_listes_electorales": True}}

client = TestClient(server.app)


def register(manifest):
    response = client.post("/catalog/register", json=manifest, headers={"Authorization": f"Bearer {server.AUTH_TOKEN}"})
    assert response.status_code == 200


def test_reads_and_executes_a_public_algorithm_without_token():
    register(MANIFEST)
    algorithm = client.get("/public/catalog/civique-droit-vote").json()
    assert algorithm["input_schema"] == MANIFEST["input_schema"]
    assert algorithm["output_schema"] == MANIFEST["output_schema"]
    result = client.post("/public/execute/civique-droit-vote", json=ELIGIBLE).json()
    assert result["status"] == "success"
    assert result["output"]["value"] is True


def test_hides_an_algorithm_that_is_not_public():
    register({**MANIFEST, "id": "civique-droit-vote-prive", "public": False})
    assert client.get("/public/catalog/civique-droit-vote-prive").status_code == 404
    assert client.post("/public/execute/civique-droit-vote-prive", json=ELIGIBLE).status_code == 404
