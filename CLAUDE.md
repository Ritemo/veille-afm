# Veille AFM

Veille techno personnelle : qui cite mes travaux, qui utilise MountainsSPIP et les logiciels concurrents, actus des constructeurs AFM, littérature sur mes thèmes. Robot Python (GitHub Actions, chaque nuit) + appli PWA. Détails dans le README.

## Qui je suis et comment je travaille

- Mathieu Cognard. Je ne suis pas développeur : je décris ce que je veux, Claude code, teste et pousse.
- Je travaille surtout depuis mon téléphone (sessions cloud Claude Code), avec un abonnement Claude Pro : économise le quota (pas de relectures inutiles de gros fichiers, pas d'outils qui consomment des tokens en arrière-plan).
- Réponds en français, simplement, sans jargon. Jamais de tiret cadratin (caractère U+2014), ni dans les réponses ni dans les fichiers.
- Uniquement des outils et services gratuits (GitHub Actions, GitHub Pages, Google Sheets, ntfy...). Si quelque chose de payant semble nécessaire, demande d'abord.
- Pousse directement sur `main` une fois les tests passés. Pas de branche ni de pull request sauf si je le demande.
- Tu peux prendre les décisions de design et proposer des améliorations : je valide ou corrige ensuite.
- Le README est écrit pour quelqu'un qui reprendrait le projet sans savoir coder : mets-le à jour quand le fonctionnement change.

## Vérifier avant de pousser

- Lance les tests du dépôt (voir ci-dessous).
- Pour toute modification d'interface, ouvre l'appli avec Playwright (MCP déclaré dans `.mcp.json`) au format téléphone (390 x 844) et vérifie l'affichage, puis au format ordinateur si l'appli s'utilise aussi sur PC.
- Pense au cache du service worker (`sw.js`) : change sa version quand les fichiers de l'appli changent, sinon les téléphones gardent l'ancienne.

## Règles propres à ce projet

- Je suis Product Manager de MountainsSPIP chez Digital Surf et chercheur AFM/nanomécanique. Chaque élément a un niveau (Critique, Haute, Moyenne, Faible) et une phrase « Pour toi » pensée pour ce rôle.
- Je consulte la veille **sur mon PC** (écran 15,6 pouces, via Chrome) : vérifier l'affichage au format ordinateur en priorité, téléphone en second.
- « SPIP (historique) » est l'ancien SPIP, prédécesseur de MountainsSPIP, pas un concurrent.
- Ne garder que les mentions de Mountains qui parlent d'AFM. Veille à partir de juillet 2026, sans doublons, réduite à l'essentiel.
- Le robot (`collector/collect.py`) est sans dépendance : garder ça. Réglages dans `config.json`.
- Pour lire une page web (site constructeur, article), utiliser le MCP `fetch` ; Playwright si la page a besoin de JavaScript.
- Synthèse hebdomadaire le lundi par mail vers ma boîte pro ; alerte mail le jour même pour les fiches Critique. Les résumés en français sont générés la nuit par une tâche Claude planifiée.
