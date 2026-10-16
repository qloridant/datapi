# pass-culture-rules

Algorithme réglementaire *pass Culture* (statut d'éligibilité), conforme à
[regalgo](https://github.com/datagouv/regalgo) : une classe exposant
`algo_id`, `regulation` et
`compute(algo_input: regalgo.AlgoInput) -> regalgo.AlgoResult`, avec un
`metadata.json` JSON-LD (vocabulaires CPRMV / Core Person / CCCEV)
colocalisé décrivant le fondement légal et les champs attendus.

Réimplémentation indépendante, dérivée du texte de loi publié, recoupée
(sans copie) avec le back-end (MPL-2.0)
[pass-culture-main](https://github.com/pass-culture/pass-culture-main).

## Algorithme disponible

| Classe | Décide | Fondement légal |
|---|---|---|
| [`statut_eligibilite.StatutEligibiliteAlgo`](src/pass_culture_rules/statut_eligibilite/regles.py) | Statut d'éligibilité par âge/date/département | Décret n° 2021-628 du 20 mai 2021 · Décret n° 2025-195 |

Ce paquet ne dépend pas de `regalgo.PublicRule` (bug de résolution du
`metadata.json`, voir `_base.py`) : le contournement est factorisé dans
`src/pass_culture_rules/_base.py`.
