"""Tests for catalog/jsonld_converter.py, using the real metadata.jsonld
Prest'Agri published for regles.data.gouv.fr (2 services under an aggregator:
quotient-familial and aide-scolarite) as the fixture -- the same file used to
produce examples/prestagri/manifest.json's package form.
"""

import json

from catalog.jsonld_converter import import_jsonld_into_manifest, manifest_to_jsonld

REAL_PRESTAGRI_METADATA_JSONLD = json.dumps({
    "@context": {
        "cpsv": "http://purl.org/vocab/cpsv#",
        "cv": "http://data.europa.eu/m8g/",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "schema": "http://schema.org/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "cprmv": "https://regels.overheid.nl/def/cprmv#",
        "px": "https://github.com/betagouv/prestagri#vocab/",
        "id": "@id",
        "type": "@type",
        "title": {"@id": "dct:title", "@language": "fr"},
        "description": {"@id": "dct:description", "@language": "fr"},
    },
    "@graph": [
        {
            "id": "https://github.com/betagouv/prestagri#service",
            "type": "cpsv:PublicService",
            "dct:hasPart": [
                {"id": "https://github.com/betagouv/prestagri#service-quotient-familial"},
                {"id": "https://github.com/betagouv/prestagri#service-aide-scolarite"},
            ],
            "dct:source": {"id": "https://github.com/betagouv/prestagri#source-code"},
        },
        {
            "id": "https://github.com/betagouv/prestagri#service-quotient-familial",
            "type": "cpsv:PublicService",
            "dct:identifier": "prestagri-quotient-familial",
            "dct:isPartOf": {"id": "https://github.com/betagouv/prestagri#service"},
            "title": "Calcul du quotient familial (QF)",
            "description": "Calcule le quotient familial d'un agent selon la note de service MASA (revenu fiscal de référence rapporté au nombre d'unités du foyer, avec majorations parent isolé / handicap / garde alternée / abattement outre-mer).",
            "cv:hasChannel": {"id": "https://github.com/betagouv/prestagri#channel-quotient-familial"},
            "dct:source": [
                {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/catala/src/commun/quotient_familial.catala_fr#CalculQuotientFamilial"},
                {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/backend/app/api/default.py#read_quotient_familial"},
            ],
            "cv:hasInput": [
                {"@type": "cprmv:Parameter", "dct:identifier": "agent_revenu", "dct:title": "Revenu de l'agent", "cprmv:definition": "Revenu fiscal de référence annuel de l'agent, en euros.", "cprmv:type": "xsd:integer", "schema:valueRequired": True},
                {"@type": "cprmv:Parameter", "dct:identifier": "garde_alternee", "dct:title": "Garde alternée", "cprmv:definition": "L'agent a un ou des enfants en garde alternée.", "cprmv:type": "xsd:boolean", "schema:valueRequired": False, "schema:defaultValue": False},
            ],
            "cpsv:produces": [
                {"@type": ["cv:Output", "cprmv:Rule"], "dct:identifier": "value", "dct:title": "Quotient familial", "cprmv:definition": "Quotient familial calculé, exprimé en euros (ex. \"812.5€\").", "cprmv:type": "xsd:string"},
            ],
        },
        {
            "id": "https://github.com/betagouv/prestagri#channel-quotient-familial",
            "type": "cv:Channel",
            "dct:identifier": "prestagri-channel-quotient-familial",
            "dct:description": {"@value": "Point d'accès HTTP GET, réponses JSON.", "@language": "fr"},
            "foaf:page": {"id": "https://api.prest-agri.beta.gouv.fr/quotient_familial"},
        },
        {
            "id": "https://github.com/betagouv/prestagri#service-aide-scolarite",
            "type": "cpsv:PublicService",
            "dct:identifier": "prestagri-aide-scolarite",
            "dct:isPartOf": {"id": "https://github.com/betagouv/prestagri#service"},
            "title": "Calcul de l'aide à la scolarité",
            "description": "Calcule le montant de l'aide à la scolarité (fiche F16) à partir du quotient familial du foyer, du barème de points (dont l'éloignement domicile-établissement) et du plafond de 1000€ par enfant et par an.",
            "cv:hasChannel": {"id": "https://github.com/betagouv/prestagri#channel-aide-scolarite"},
            "dct:source": [
                {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/catala/src/aide_scolarite/aide_scolarite.catala_fr#CalculAideScolarite"},
                {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/backend/app/api/default.py#read_quotient_familial_aide_scolarite"},
            ],
            "cv:hasInput": [
                {"@type": "cprmv:Parameter", "dct:identifier": "agent_revenu", "dct:title": "Revenu de l'agent", "cprmv:definition": "Revenu fiscal de référence annuel de l'agent, en euros.", "cprmv:type": "xsd:integer", "schema:valueRequired": True},
                {"@type": "cprmv:Parameter", "dct:identifier": "garde_alternee", "dct:title": "Garde alternée", "cprmv:definition": "L'agent a un ou des enfants en garde alternée.", "cprmv:type": "xsd:boolean", "schema:valueRequired": False, "schema:defaultValue": False},
                {"@type": "cprmv:Parameter", "dct:identifier": "parent_isole", "dct:title": "Parent isolé", "cprmv:definition": "L'agent est parent isolé au sens fiscal.", "cprmv:type": "xsd:boolean", "schema:valueRequired": False, "schema:defaultValue": False},
                {"@type": "cprmv:Parameter", "dct:identifier": "outre_mer", "dct:title": "Outre-mer", "cprmv:definition": "L'agent est affecté en outre-mer.", "cprmv:type": "xsd:boolean", "schema:valueRequired": False, "schema:defaultValue": False},
                {"@type": "cprmv:Parameter", "dct:identifier": "montant_materiel_specifique", "dct:title": "Matériel spécifique", "cprmv:definition": "Montant des frais d'équipement scolaire obligatoire engagés, en euros.", "cprmv:type": "xsd:integer", "schema:valueRequired": False},
            ],
            "cpsv:produces": [
                {"@type": ["cv:Output", "cprmv:Rule"], "dct:identifier": "value", "dct:title": "Montant de l'aide", "cprmv:definition": "Montant de l'aide à la scolarité calculé, plafonné à 1000€ par enfant et par an, exprimé en euros.", "cprmv:type": "xsd:string"},
            ],
        },
        {
            "id": "https://github.com/betagouv/prestagri#channel-aide-scolarite",
            "type": "cv:Channel",
            "dct:identifier": "prestagri-channel-aide-scolarite",
            "dct:description": {"@value": "Point d'accès HTTP GET, réponses JSON.", "@language": "fr"},
            "foaf:page": {"id": "https://api.prest-agri.beta.gouv.fr/aide_scolarite"},
        },
        {
            "id": "https://github.com/betagouv/prestagri#source-code",
            "type": "schema:SoftwareSourceCode",
            "schema:name": "Prest'Agri - moteur de calcul",
            "schema:codeRepository": "https://github.com/betagouv/prestagri/tree/478b3cc2ab28299c73b94fdd192b0559ae5873b8",
            "schema:programmingLanguage": ["Python", "Catala"],
            "schema:runtimePlatform": ["Python >= 3.13 (gestionnaire de paquets uv)"],
            "schema:softwareRequirements": ["fastapi[standard] >= 0.136.1"],
            "schema:softwareVersion": "0.1.0",
            "px:howTo": {"@type": "schema:HowTo", "schema:name": "Installer et exécuter Prest'Agri"},
        },
    ],
})


def _original_aide_scolarite_package(**algorithm_overrides):
    """The aide-scolarite algorithm entry as it existed before this migration
    (see examples/prestagri/manifest.json git history) -- pre-identified for
    import (dct:identifier set), everything CPSV-AP-derived still missing."""
    algorithm = {
        "id": "examples.sample.aide_scolarite_prestagri",
        "dct:identifier": "prestagri-aide-scolarite",
        "runtime": {"language": "catala", "version": "dev"},
        "entrypoint": {"type": "catala:scope", "target": "examples.prestagri.generated.Aide_scolarite:calcul_aide_scolarite"},
        "input_schema": {
            "type": "object",
            "properties": {
                "foyer_fiscal_agent": {
                    "type": "object",
                    "properties": {
                        "garde_alternee": {"type": "boolean"},
                        "parent_isole": {"type": "boolean"},
                        "outre_mer": {"type": "boolean"},
                    },
                },
                "montant_materiel_specifique": {"type": "number"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "aide_scolarite": {"type": "number"},
            },
        },
    }
    algorithm.update(algorithm_overrides)
    return {"org": "betagouv.prestagri", "algorithms": [algorithm]}


def test_import_gap_fills_matched_entry_and_warns_about_unmatched_service():
    package, warnings = import_jsonld_into_manifest(
        _original_aide_scolarite_package(), REAL_PRESTAGRI_METADATA_JSONLD
    )

    entry = package["algorithms"][0]
    assert entry["dct:title"] == "Calcul de l'aide à la scolarité"
    assert entry["description"].startswith("Calcule le montant de l'aide à la scolarité")
    assert entry["cv:hasChannel"] == {
        "foaf:page": "https://api.prest-agri.beta.gouv.fr/aide_scolarite",
        "dct:description": "Point d'accès HTTP GET, réponses JSON.",
    }
    assert entry["dct:source"] == [
        {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/catala/src/aide_scolarite/aide_scolarite.catala_fr#CalculAideScolarite"},
        {"id": "https://github.com/betagouv/prestagri/blob/478b3cc2ab28299c73b94fdd192b0559ae5873b8/backend/app/api/default.py#read_quotient_familial_aide_scolarite"},
    ]

    assert any("prestagri-quotient-familial" in w for w in warnings)


def test_import_never_overwrites_an_existing_field():
    package, _ = import_jsonld_into_manifest(
        _original_aide_scolarite_package(**{"dct:title": "Nom déjà présent"}), REAL_PRESTAGRI_METADATA_JSONLD
    )

    assert package["algorithms"][0]["dct:title"] == "Nom déjà présent"


def test_import_fills_nested_schema_titles_without_overwriting():
    package = _original_aide_scolarite_package()
    package["algorithms"][0]["input_schema"]["properties"]["foyer_fiscal_agent"]["properties"]["outre_mer"]["title"] = "Titre déjà présent"

    package, _ = import_jsonld_into_manifest(package, REAL_PRESTAGRI_METADATA_JSONLD)

    entry = package["algorithms"][0]
    foyer = entry["input_schema"]["properties"]["foyer_fiscal_agent"]["properties"]
    assert foyer["garde_alternee"]["title"] == "Garde alternée"
    assert foyer["parent_isole"]["description"] == "L'agent est parent isolé au sens fiscal."
    # already had its own title -> must not be overwritten by the jsonld's title
    assert foyer["outre_mer"]["title"] == "Titre déjà présent"
    assert entry["input_schema"]["properties"]["montant_materiel_specifique"]["title"] == "Matériel spécifique"


def test_import_ambiguous_match_raises_value_error():
    package = {
        "algorithms": [
            {"id": "a", "runtime": {"language": "python"}, "entrypoint": {"type": "python:function", "target": "m:f"},
             "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
            {"id": "b", "runtime": {"language": "python"}, "entrypoint": {"type": "python:function", "target": "m:g"},
             "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
        ]
    }

    try:
        import_jsonld_into_manifest(package, REAL_PRESTAGRI_METADATA_JSONLD)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "ambiguous" in str(e)


def test_manifest_to_jsonld_round_trips_imported_fields():
    package, _ = import_jsonld_into_manifest(_original_aide_scolarite_package(), REAL_PRESTAGRI_METADATA_JSONLD)

    jsonld = manifest_to_jsonld(package)
    service = next(n for n in jsonld["@graph"] if n.get("dct:identifier") == "prestagri-aide-scolarite")

    assert service["dct:title"] == "Calcul de l'aide à la scolarité"
    assert service["dct:description"].startswith("Calcule le montant de l'aide à la scolarité")
    assert service["cv:hasChannel"] == {
        "foaf:page": "https://api.prest-agri.beta.gouv.fr/aide_scolarite",
        "dct:description": "Point d'accès HTTP GET, réponses JSON.",
    }
    assert service["dct:source"] == package["algorithms"][0]["dct:source"]


def test_manifest_to_jsonld_single_algorithm_has_no_aggregator():
    algorithm = _original_aide_scolarite_package()["algorithms"][0]

    jsonld = manifest_to_jsonld(algorithm)

    assert len(jsonld["@graph"]) == 1
    assert jsonld["@graph"][0]["@type"] == "cpsv:PublicService"
