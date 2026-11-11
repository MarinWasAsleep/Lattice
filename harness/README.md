# DitherCraft : kit de pilotage du harness IA

Ce dossier contient tout ce qu'il faut pour faire développer DitherCraft par un harness à deux modèles :
un **codeur** bon marché (DeepSeek v4.1 flash) et un **relecteur** (Sonnet). Les documents lus par les
modèles sont en anglais : c'est plus économe en tokens et plus fiable pour du code. Ce README est pour toi.

## Fichiers

| Fichier | Lu par | Rôle |
|---|---|---|
| `CONTRACT.md` | codeur (extraits), relecteur (extraits), orchestrateur | Source de vérité technique : arborescence, types, signatures, règles, gates. Versionné. |
| `TASKS.md` | orchestrateur | Les 18 cartes de tâches (T00 à T16, T07 scindée en A et B) : dépendances, vagues, fichiers possédés, critères d'acceptation. |
| `STATE.md` | orchestrateur, toi | Registre vivant : statut des tâches, version du contrat, décisions. |
| `DEVIATIONS.md` | orchestrateur, relecteur, toi | Protocole de gestion des écarts + registre. |
| `prompts/ORCHESTRATOR.md` | orchestrateur | Prompt de départ : lit l'état, choisit les tâches prêtes, génère les prompts suivants. |
| `prompts/CODER.md` | codeur | Gabarit du prompt de tâche (rempli par l'orchestrateur). |
| `prompts/REVIEWER.md` | relecteur | Gabarit du prompt de revue. |

## Boucle d'exécution

```
           ┌──────────────────────────────────────────────────────────┐
           ▼                                                          │
 ORCHESTRATEUR ── lit STATE + TASKS + écarts ouverts                  │
           │  émet : prompts codeur (≤ 4 en parallèle) + patch STATE  │
           ▼                                                          │
 CODEUR (DeepSeek) ── écrit uniquement ses fichiers possédés          │
           ▼                                                          │
 GATES automatiques (0 token) : G1 ruff → G2 pytest → G3 contrat      │
           │                    → G4 propriété des fichiers           │
           │  échec → retour au codeur avec le log (pas d'appel Sonnet)
           ▼                                                          │
 RELECTEUR (Sonnet) ── diff + résultats de tests + extrait du contrat │
           │  PASS → commit, tâche « done »                           │
           │  FIX  → retour codeur avec findings                      │
           │  ESCALATE → écart E2/E4/E5 → orchestrateur ou toi        │
           └──────────────────────────────────────────────────────────┘
```

## Principes d'économie (pourquoi le kit est construit ainsi)

1. **Les tests coûtent zéro token.** Les gates G1 à G4 sont exécutés par le harness. Sonnet n'est
   appelé que sur du code qui compile, passe ses tests et respecte le contrat. C'est le levier principal.
2. **Contexte minimal par tâche.** Chaque carte de tâche liste les sections du contrat (`context:`)
   à injecter. Le codeur ne voit jamais le dépôt entier ; le relecteur ne voit que le diff.
3. **Préfixe stable.** Les gabarits placent les règles fixes et les extraits de contrat en tête,
   le contenu variable en fin. Si ton fournisseur propose un cache de préfixe, il est exploité.
4. **Propriété exclusive des fichiers.** T01 crée tous les fichiers sous forme de stubs ; chaque tâche
   ne modifie que les siens. Résultat : pas de conflit de fusion, parallélisme sans coordination.
5. **Revue proportionnée au risque.** `strict` pour les fondations (T01, T08, T09, T14), `full` pour
   l'algorithmique et l'UI, `light` pour les données et le packaging.
6. **Fichiers courts.** Au plus 400 lignes : un modèle léger réécrit le fichier entier sans dériver.
7. **Escalade bornée.** Au plus 3 boucles gates et 2 cycles de revue par tâche, puis Sonnet corrige
   lui-même ou t'escalade. Pas de boucle infinie payante.

## Graphe de dépendances et parallélisme

```
T00 (env + sonde protocole, humain + Sonnet)
 └─ T01 (squelette + noyau ; CONTRAT GELÉ ensuite)
     ├─ VAGUE 1, tout en parallèle (fichiers disjoints) :
     │   T02 diffusion d'erreur   T03 ordonné       T04 divers + halftone
     │   T05 palettes intégrées   T06 extraction    T07A effets tons
     │   T07B effets glitch       T08 pont PhotoCraft   T09 pipeline + presets
     │   T10 shell UI + canvas
     ├─ VAGUE 2 (après T09 + T10), en parallèle :
     │   T11 panneau algorithme   T12 panneau effets   T13 panneau palette
     └─ VAGUE 3, séquentielle :
         T14 intégration (après tout) → T15 packaging → T16 recette dans PhotoCraft
```

- **Chemin critique** : T00 → T01 → T09 → T11/T12/T13 → T14 → T15 → T16. Priorise toujours T09 dans la vague 1.
- **Doivent être faites seules** : T00 (décisions d'environnement), T01 (tout en dépend), T14 (touche
  au câblage global), T16 (recette).
- **Concurrence conseillée** : 4 tâches à la fois au maximum. Au-delà, la file de revue Sonnet
  devient le goulot et les écarts découverts tard coûtent plus cher.
- T02 à T07B n'ont besoin que du registre (T01) : elles peuvent tourner pendant que T09 avance.

## Points de contrôle humains

| Id | Quand | Ce que tu fais |
|---|---|---|
| H0 | Pendant T00 | Approuver l'installation (venv, paquets ; Python 3.13 si 3.15 n'est pas supporté). Configurer la read root d'automatisation dans PhotoCraft. |
| H1 | Après T01 | Lire `CONTRACT.md` final et le geler (5 minutes, c'est la décision la plus rentable du projet). |
| H2 | Après la vague 2 | Lancer l'UI, juger l'ergonomie, noter les retouches. |
| H3 | T15 | Approuver la création des raccourcis Bureau et menu Démarrer. |
| H4 | T16 | Recette dans PhotoCraft réel. |

## Risques identifiés

| Id | Risque | Statut | Parade |
|---|---|---|---|
| R1 | numba ou PySide6 sans wheel pour Python 3.15.2 | [incertain] | T00 teste ; repli : Python 3.13 via `py` (avec ta confirmation). |
| R2 | Authentification par jeton sur TCP inconnue | [à vérifier] | T00 sonde avec un appel `methods` en lecture seule. |
| R3 | `doc.place` exige une automation read root sur l'app desktop | [vérifié en headless] | T00 : tu la règles dans PhotoCraft ; le dossier d'échange est fixé dans le contrat §8. |
| R4 | Le calque placé est un Smart Object | [vérifié] | T00 teste `layer.rasterize.layer` via `engine.execute` ; sinon on garde le Smart Object (acceptable). |
| R5 | Valeurs hexadécimales de palettes hallucinées par le codeur | probable | Les palettes sûres sont fournies en dur dans T05 ; les autres exigent une source citée ou sont exclues. |
| R6 | Lenteur de l'aperçu sur grandes images | probable | Proxy `max_side=1024`, worker « le dernier gagne », debounce 120 ms. |
| R7 | Threading Qt (widgets touchés depuis le worker) | classique | Règle explicite §9 + revue `strict` sur T14. |

## Comment démarrer

1. Exécuter T00 avec Sonnet (ou avec moi) : c'est la seule tâche qui touche au système.
2. Lancer l'orchestrateur avec `prompts/ORCHESTRATOR.md`, section KICKOFF.
3. Ensuite, à chaque événement (gates terminés, verdict de revue), relancer l'orchestrateur avec la
   section CYCLE et l'événement. Il renvoie le patch de STATE et les prompts suivants.

Remarque : les étapes « choisir les tâches prêtes » et « remplir le gabarit » sont déterministes.
Une fois le flux rodé, un script de 100 lignes peut les remplacer et réserver l'orchestrateur LLM
aux écarts. C'est l'optimisation suivante la plus rentable.
