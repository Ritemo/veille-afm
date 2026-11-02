# Veille AFM

Veille personnelle : qui cite mes travaux, qui utilise Mountains (et les logiciels concurrents), les actus des constructeurs AFM et la littérature sur mes thèmes. Un robot collecte chaque matin, l'appli (PWA) affiche le tout.

## Fonctionnement

| Élément | Rôle |
|---|---|
| `collector/collect.py` | Robot (Python, sans dépendance). Interroge OpenAlex, Europe PMC (plein texte, utile pour les sections Méthodes), arXiv et Google Actualités, note chaque élément, fusionne dans `data/items.json` |
| `config.json` | Tout ce qui se règle : mots-clés, thèmes, constructeurs, logiciels suivis, revues majeures, fenêtres de temps |
| `.github/workflows/collecte.yml` | Lance le robot chaque nuit vers 2h20 et enregistre les données |
| `index.html` + `sw.js` + `manifest.webmanifest` | L'appli, hébergée sur GitHub Pages, installable sur Android |
| `data/abstracts.json` | Résumés complets en anglais, écrits par le robot, lus par la tâche de nuit |
| `data/resumes.json` | Résumés en français, titre traduit, infos utiles et accès libre, écrits chaque nuit par une tâche planifiée Claude (40 éléments par nuit, les plus importants d'abord) |
| `data/synthese.md` | Synthèse hebdomadaire du lundi, affichée en tête de « À la une » et envoyée par mail |

### L'importance pour le PM AFM (Critique, Haute, Moyenne, Faible)
Chaque élément reçoit un niveau et une phrase « Pour toi » qui dit pourquoi ça compte pour MountainsSPIP. Exemples : un constructeur qui annonce du logiciel ou de l'automatisation est Critique, un nouveau mode matériel est Haute (vérifier l'import des fichiers), un concurrent utilisé sur une analyse couverte par Mountains est Haute, des résultats financiers sont Faible. Les règles sont dans `importance_pm()` du robot. « À la une » affiche Haute et Critique des 14 derniers jours ; le bouton de niveau filtre tous les onglets.

### Le score (0 à 100)
Base selon la catégorie (citation de mes travaux 60, logiciels 40, constructeurs 30, littérature 20), +10 par mot-clé prioritaire trouvé (max +30), +20 si Mountains est cité, +10 revue majeure, bonus selon le nombre de citations, +20 pour une annonce produit chez un constructeur. « À la une » montre ce qui dépasse 50 sur les 14 derniers jours.

## Mise en ligne (une seule fois)

1. Créer un dépôt **Ritemo/veille-afm** sur GitHub (public, nécessaire pour GitHub Pages en offre gratuite) et y pousser ces fichiers.
2. **Settings > Actions > General > Workflow permissions** : cocher « Read and write permissions ».
3. **Actions > Collecte veille AFM > Run workflow** pour le premier passage (il remonte 90 jours en arrière).
4. **Settings > Pages** : Source « Deploy from a branch », branche `main`, dossier `/ (root)`.
5. L'appli est alors sur `https://ritemo.github.io/veille-afm/`. Pour l'APK : la passer dans PWABuilder, comme pour l'appli hand.

## Réglages courants

- `imp_min` (dans `config.json`) : niveau minimal gardé (2 = Moyenne). Les fiches Faible, les doublons (même titre, prépublication puis revue) et les citations ne sont plus conservés.
- `date_min` (dans `config.json`) : rien d'antérieur à cette date de publication n'est collecté ni gardé. Pour appliquer un changement de règles aux données sans relancer la collecte : `python collector/collect.py --nettoyer`.
- Anti-bruit : « SPIP » n'est gardé qu'avec un vrai contexte AFM, « Park Systems » seulement pour la société (pas les parcs). Gwyddion et NanoScope Analysis sans analyse que MountainsSPIP met en avant passent en Faible.
- Dans l'appli : tri par importance ou par date de publication, et filtre de période (7 j, 30 j, tout).

- Ajouter un thème : une ligne dans `themes_afm` (nom affiché : requête OpenAlex).
- Trop de bruit sur un logiciel (Gwyddion est très cité) : le retirer de `logiciels` ou baisser `max_par_requete`.

Les statuts « lu » et « à creuser » sont gardés dans le téléphone (stockage local du navigateur).
