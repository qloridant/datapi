"""
Base commune, interne, à toutes les règles de ce paquet.

``regalgo.PublicRule.__init__`` résout ``metadata.json`` via
``Path(__file__).parent`` — mais ``__file__``, à l'intérieur d'une méthode
définie dans ``regalgo/standard_rules.py``, désigne toujours ce fichier-là,
pas celui de la sous-classe qui hérite de ``PublicRule``. Hériter de
``PublicRule`` sans redéfinir ``__init__`` lève donc un
``FileNotFoundError`` (vérifié empiriquement avec regalgo 0.0.3/0.0.4).
C'est pour cette raison que l'exemple qui fonctionne réellement dans cet
écosystème (``regalgo_civique_droit_vote.DroitVoteAlgorithm``) n'hérite pas
de ``PublicRule`` et redéfinit ``__init__``/``algo_id``/``regulation`` en
propre, avec son propre ``Path(__file__)``.

Ce module reproduit la même forme (``algo_id``, ``regulation``,
``compute(AlgoInput) -> AlgoResult`` à implémenter par chaque règle), sans
hériter de ``PublicRule``, mais évite de dupliquer le bloc
``__init__``/``algo_id``/``regulation`` dans chaque fichier ``regles.py``
en le factorisant ici — chaque sous-classe n'a qu'à passer son propre
répertoire explicitement, ce qui contourne le bug sans le reproduire.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BaseRule:
    """À sous-classer par chaque règle ; voir le docstring du module."""

    def __init__(self, metadata_dir: Path) -> None:
        metadata_path = metadata_dir / "metadata.json"
        self._metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))

    @property
    def algo_id(self) -> str:
        return self._metadata["dct:identifier"]

    @property
    def regulation(self) -> dict[str, Any]:
        return self._metadata["cprmv:isBasedOn"]
