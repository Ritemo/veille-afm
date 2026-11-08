---
name: modele-appli
description: Modèle d'appli de Mathieu (robot GitHub Actions + PWA sur GitHub Pages + Google Sheets ou JSON, notifications ntfy). À utiliser pour créer une nouvelle appli ou ajouter un robot ou un écran à une appli existante.
---

# Le modèle d'appli de Mathieu

Toutes ses applis (stats-hand, stats-n3f, paris-foot, veille-afm) suivent le même schéma. Pour une nouvelle appli, repartir de ce modèle et s'inspirer du dépôt existant le plus proche plutôt que de tout réinventer.

## Architecture

```
Source de données (site, API gratuite, feuille de match...)
   │  robot : GitHub Actions planifié (Python, dépendances minimales)
   ▼
Stockage : Google Sheets publié en CSV (données saisies à la main aussi)
           ou fichiers JSON dans le dépôt (données produites par le robot seul)
   │
   ▼
Appli PWA statique (index.html + sw.js + manifest) sur GitHub Pages
   └─ notifications ntfy.sh (sujets avec suffixe aléatoire)
```

- Dépôt **public** sur le compte GitHub `Ritemo` (GitHub Pages gratuit). Jamais de secret dans le code : clés et compte de service Google dans *Settings > Secrets and variables > Actions*.
- Données privées (exemple : budget) : pas de dépôt public ni de CSV publié. Utiliser un Google Apps Script privé (un seul utilisateur, lui).
- Tout doit rester **gratuit**. Vérifier les quotas des API gratuites et prévoir un mode économe.

## Robot

- Les `cron` de GitHub Actions sont en **UTC** : commenter l'heure de Paris à côté, en pensant au passage heure d'été / heure d'hiver.
- Éviter les minutes rondes (:00, :30), souvent retardées ; prévoir des passages de secours les jours importants.
- Écrire un journal (onglet ou fichier) de ce que le robot a fait, et envoyer une alerte ntfy sur un sujet « alerte » en cas d'erreur ou de donnée absente.

## Appli

- Fichiers statiques, sans framework ni étape de build. Mobile d'abord (390 x 844), sauf si l'appli se consulte surtout sur PC (cas de veille-afm).
- Design clair et attractif, en français. Mathieu laisse Claude proposer le design.
- Changer la version du cache dans `sw.js` à chaque modification, sinon les téléphones gardent l'ancienne version.
- APK Android si besoin : convertir la PWA avec PWABuilder.

## Qualité et mise en ligne

- Un workflow de vérification (`verif-deploy.yml` ou `tests.yml`) lance les tests à chaque push et envoie une alerte ntfy si ça échoue.
- Avant de pousser : tests du dépôt, puis vérification visuelle avec Playwright (MCP).
- Pousser directement sur `main`.

## README

Écrit pour quelqu'un qui reprendrait l'appli **sans savoir coder** : schéma de fonctionnement, installation pas à pas depuis l'interface web de GitHub (*Add file > Upload files*, secrets, activation de Pages), gestes courants, nouvelle saison, que faire en cas d'alerte.
