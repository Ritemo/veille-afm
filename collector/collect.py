#!/usr/bin/env python3
"""Robot de veille AFM.

Collecte les nouveautés (articles, mentions de logiciels, actus constructeurs),
les note avec des règles simples et les fusionne dans data/items.json.
Bibliothèque standard uniquement : rien à installer dans GitHub Actions.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER_CONFIG = os.path.join(RACINE, "config.json")
FICHIER_ITEMS = os.path.join(RACINE, "data", "items.json")
FICHIER_META = os.path.join(RACINE, "data", "meta.json")
FICHIER_RESUMES_EN = os.path.join(RACINE, "data", "abstracts.json")  # résumés complets pour la tâche de nuit
FICHIER_EXCLUS = os.path.join(RACINE, "data", "exclusions.json")  # fiches marquées « Pas pertinent » dans l'appli

VERSION_REQUETES = 4  # à incrémenter quand les requêtes changent
UA = "veille-afm/1.0 (robot personnel de veille scientifique)"
AUJOURDHUI = dt.date.today()
erreurs = []


# ---------------------------------------------------------------- outils
def http_get(url, essais=3):
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == essais - 1:
                raise
            time.sleep(2 * (i + 1))
    return b""


def get_json(url):
    return json.loads(http_get(url).decode("utf-8"))


def propre(texte, n=None):
    if not texte:
        return ""
    t = html.unescape(re.sub(r"<[^>]+>", " ", str(texte)))
    t = re.sub(r"\s+", " ", t).strip()
    if n and len(t) > n:
        t = t[: n - 1].rsplit(" ", 1)[0] + "…"
    return t


def norm_doi(doi):
    if not doi:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower())


def cle(item):
    if item.get("doi"):
        return "doi:" + item["doi"]
    titre = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:80]
    return "t:" + hashlib.sha1(titre.encode()).hexdigest()[:16]


def resume_openalex(inv):
    if not inv:
        return ""
    pos = []
    for mot, idx in inv.items():
        for i in idx:
            pos.append((i, mot))
    return " ".join(m for _, m in sorted(pos))


def item(cat, titre, url, date, source, **kw):
    it = {
        "cat": cat,
        "title": propre(titre, 300),
        "url": url or "",
        "date": (date or "")[:10],
        "source": source,
        "authors": propre(kw.get("authors", ""), 160),
        "venue": propre(kw.get("venue", ""), 120),
        "abstract": propre(kw.get("abstract", ""), 320),
        "doi": norm_doi(kw.get("doi", "")),
        "cited_by": int(kw.get("cited_by") or 0),
        "group": kw.get("group", ""),
        "oa": kw.get("oa"),            # True gratuit, False payant, None inconnu
        "oa_url": kw.get("oa_url") or "",
    }
    it["id"] = cle(it)
    it["_abs"] = propre(kw.get("abstract", ""), 2500)
    return it


# ---------------------------------------------------------------- sources
def openalex_recherche(cfg, requete, depuis, cat, group):
    params = {
        "search": requete,
        "filter": f"from_publication_date:{depuis}",
        "sort": "publication_date:desc",
        "per-page": str(cfg["max_par_requete"] if cat != "logiciels" else cfg["max_par_requete_logiciels"]),
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    return [openalex_vers_item(w, cat, group) for w in get_json(url).get("results", [])]


def openalex_vers_item(w, cat, group):
    loc = (w.get("primary_location") or {})
    src = (loc.get("source") or {})
    auteurs = ", ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:4]
                        if a.get("author"))
    if len(w.get("authorships") or []) > 4:
        auteurs += " et al."
    url = w.get("doi") or loc.get("landing_page_url") or w.get("id")
    return item(cat, w.get("display_name") or "", url, w.get("publication_date"), "OpenAlex",
                authors=auteurs, venue=src.get("display_name", ""),
                abstract=resume_openalex(w.get("abstract_inverted_index")),
                doi=w.get("doi"), cited_by=w.get("cited_by_count"), group=group,
                oa=(w.get("open_access") or {}).get("is_oa"),
                oa_url=(w.get("open_access") or {}).get("oa_url")
                or ((w.get("best_oa_location") or {}).get("pdf_url")))


def europepmc_recherche(cfg, requete, depuis, cat, group):
    q = f"({requete}) AND FIRST_PDATE:[{depuis} TO {AUJOURDHUI.isoformat()}]"
    taille = cfg["max_par_requete"] if cat != "logiciels" else cfg["max_par_requete_logiciels"]
    params = {"query": q, "format": "json", "pageSize": str(taille),
              "resultType": "core", "sort": "P_PDATE_D desc"}
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params)
    out = []
    for r in get_json(url).get("resultList", {}).get("result", []):
        doi = r.get("doi", "")
        lien = f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
        libre = r.get("isOpenAccess") == "Y" or r.get("inEPMC") == "Y"
        oa_url = ""
        for u in (r.get("fullTextUrlList") or {}).get("fullTextUrl", []):
            if u.get("availabilityCode") in ("OA", "F"):
                oa_url = u.get("url", "")
                libre = True
                break
        if libre and not oa_url and r.get("pmcid"):
            oa_url = f"https://europepmc.org/article/PMC/{r['pmcid']}"
        out.append(item(cat, r.get("title", ""), lien, r.get("firstPublicationDate"), "Europe PMC",
                        authors=r.get("authorString", ""), venue=r.get("journalTitle", ""),
                        abstract=r.get("abstractText", ""), doi=doi,
                        cited_by=r.get("citedByCount"), group=group,
                        oa=True if libre else None, oa_url=oa_url))
    return out


def arxiv_recherche(cfg, requete, depuis):
    params = {"search_query": requete, "sortBy": "submittedDate", "sortOrder": "descending",
              "max_results": str(cfg["max_par_requete"])}
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    racine = ET.fromstring(http_get(url))
    out = []
    for e in racine.findall("a:entry", ns):
        date = (e.findtext("a:published", "", ns) or "")[:10]
        if date and date < depuis:
            continue
        auteurs = [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]
        aff = ", ".join(auteurs[:4]) + (" et al." if len(auteurs) > 4 else "")
        out.append(item("litterature", e.findtext("a:title", "", ns), e.findtext("a:id", "", ns),
                        date, "arXiv", authors=aff, venue="arXiv (prépublication)",
                        abstract=e.findtext("a:summary", "", ns),
                        doi=e.findtext("x:doi", "", ns), group="arXiv",
                        oa=True, oa_url=e.findtext("a:id", "", ns).replace("/abs/", "/pdf/")))
    return out


def gnews(requete, depuis, group):
    jours = max(1, (AUJOURDHUI - dt.date.fromisoformat(depuis)).days)
    q = f"{requete} when:{jours}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    racine = ET.fromstring(http_get(url))
    out = []
    for it in racine.iter("item"):
        try:
            date = email.utils.parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:  # noqa: BLE001
            date = ""
        titre = it.findtext("title", "")
        media = it.findtext("source", "")
        if media and titre.endswith(" - " + media):
            titre = titre[: -len(media) - 3]
        out.append(item("constructeurs", titre, it.findtext("link", ""), date, "Google Actualités",
                        venue=media, group=group, oa=True))
    return out


def github_releases(depot, depuis, nom):
    """Versions publiées d'un logiciel libre hébergé sur GitHub."""
    req = urllib.request.Request(f"https://api.github.com/repos/{depot}/releases?per_page=10",
                                 headers={"User-Agent": UA, "Accept": "application/vnd.github+json",
                                          **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]}
                                             if os.environ.get("GITHUB_TOKEN") else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        rels = json.loads(r.read().decode("utf-8"))
    out = []
    for rel in rels:
        date = (rel.get("published_at") or "")[:10]
        if rel.get("draft") or not date or date < depuis:
            continue
        version = rel.get("tag_name") or rel.get("name") or ""
        titre = f"{nom} {version}" + (f" : {rel['name']}" if rel.get("name") and rel["name"] != version else "")
        out.append(item("sorties", titre, rel.get("html_url"), date, "GitHub",
                        venue=f"github.com/{depot}", abstract=rel.get("body") or "", group=nom, oa=True))
    return out


def gwyddion_versions(depuis):
    """Nouvelles versions de Gwyddion (fichiers publiés sur SourceForge)."""
    racine = ET.fromstring(http_get("https://sourceforge.net/projects/gwyddion/rss?path=/gwyddion"))
    vues, out = set(), []
    for it in racine.iter("item"):
        m = re.search(r"/gwyddion/(\d+\.\d+(?:\.\d+)?)/", it.findtext("title", "") + "/")
        if not m or m.group(1) in vues:
            continue
        try:
            date = email.utils.parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:  # noqa: BLE001
            continue
        if date < depuis:
            continue
        vues.add(m.group(1))
        out.append(item("sorties", f"Gwyddion {m.group(1)}", f"https://sourceforge.net/projects/gwyddion/files/gwyddion/{m.group(1)}/",
                        date, "SourceForge", venue="gwyddion.net", group="Gwyddion", oa=True))
    return out


def gnews_sorties(requete, depuis, group):
    out = gnews(requete, depuis, group)
    for it in out:
        it["cat"] = "sorties"
    return out


def citations(cfg, depuis):
    """Travaux qui citent les articles de l'auteur suivi (ou des DOI listés)."""
    works = []
    if cfg.get("auteur_suivi"):
        url = "https://api.openalex.org/authors?" + urllib.parse.urlencode(
            {"search": cfg["auteur_suivi"], "per-page": "5"})
        for a in get_json(url).get("results", []):
            if a.get("display_name", "").lower() != cfg["auteur_suivi"].lower():
                continue
            aid = a["id"].rsplit("/", 1)[-1]
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
                {"filter": f"author.id:{aid}", "per-page": "50", "select": "id,display_name"})
            works += get_json(url).get("results", [])
    for doi in cfg.get("dois_suivis", []):
        try:
            works.append(get_json("https://api.openalex.org/works/doi:" + norm_doi(doi)))
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"DOI {doi} : {e}")
    out = []
    for w in works:
        wid = w["id"].rsplit("/", 1)[-1]
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"filter": f"cites:{wid},from_publication_date:{depuis}", "per-page": "50"})
        for c in get_json(url).get("results", []):
            out.append(openalex_vers_item(c, "citations", "Cite : " + propre(w.get("display_name"), 70)))
    return out


# ---------------------------------------------------------------- notation
def noter(it, cfg):
    base = {"citations": 60, "sorties": 50, "logiciels": 40, "constructeurs": 30, "litterature": 20}[it["cat"]]
    texte = (it["title"] + " " + it["abstract"]).lower()
    tags = [m for m in cfg["mots_cles_prioritaires"] if m.lower() in texte]
    s = base + min(30, 10 * len(tags))
    if it["cat"] == "logiciels" and it["group"] == "Mountains":
        s += 20
    if it["cited_by"]:
        s += min(15, round(5 * math.log10(1 + it["cited_by"])))
    if any(r.lower() == it["venue"].lower() for r in cfg["revues_majeures"]):
        s += 10
        tags.append("revue majeure")
    if it["cat"] in ("constructeurs", "sorties"):
        mots = re.findall(r"[a-zà-ÿ]+", it["title"].lower())
        if any(m in mots for m in cfg["mots_annonce_produit"]):
            s += 20
            tags.append("annonce")
    it["score"] = min(100, s)
    it["tags"] = tags
    it["imp"], it["pm"] = importance_pm(it, texte, tags)
    return it


# ---------------------------------------------------------------- importance Product Manager
# 4 = critique, 3 = haute, 2 = moyenne, 1 = faible, vu depuis le poste de PM AFM chez Digital Surf
RE_LOGICIEL = r"software|analysis|analytics|automat|\bai\b|artificial intelligence|machine learning|data|algorithm|platform"
RE_MATERIEL = r"\bafm\b|atomic force|microscop|probe|cantilever|\bmode\b|nanoir|afm-ir|s-snom|scanner"
RE_STRATEGIE = r"acqui|merger|partner|collaborat|agreement|rachat|partenariat"
RE_FINANCE = (r"results|revenue|earnings|quarter|dividend|stock|shares|guidance|résultats|estimates|"
              r"\(brkr\)|krx:|wall street|market (size|analysis|report|share|trends)|quote, rfq")
RE_FONCTION = (r"force curve|force-distance|nanodma|viscoelast|contact resonance|maugis|\bjkr\b|\bdmt\b|hertz|"
               r"critical dimension|roughness|correlative|multichannel|multi-channel|segmentation")
RE_AFM = r"\bafm\b|atomic force|scanning probe|\bspm\b|nanoindent|kelvin probe|\bkpfm\b|force spectroscopy|cantilever"
RE_ML_AFM = (r"afm (image|data|map|topograph)|atomic force microscop[a-z]* (image|data|map)|force curve|"
             r"force-distance|force map|height map|topograph|cantilever")
RE_ML = r"machine learning|deep learning|neural|random forest|automat|artificial intelligence"


def importance_pm(it, texte, tags):
    cat, grp, t = it["cat"], it["group"], texte
    majeure = "revue majeure" in tags
    a = lambda r: re.search(r, t) is not None  # noqa: E731

    if cat == "citations":
        if "mountains" in t:
            return 4, "Ton travail est cité ET Mountains est mentionné : cas d'usage idéal à valoriser."
        return 3, "Ton travail est cité : contact à prendre, preuve de crédibilité scientifique."

    if cat == "logiciels":
        if grp.startswith("SPIP"):
            return 3, "Utilisateur de l'ancien SPIP : cible de migration vers MountainsSPIP, contact ou argumentaire de mise à jour."
        if grp == "Mountains":
            if "spip" in t or a(RE_AFM):
                if majeure or it["cited_by"] >= 10:
                    return 4, "MountainsSPIP ou Mountains en AFM dans une publication visible : référence client, argument commercial, note d'application."
                return 3, "Mountains utilisé en AFM : référence client MountainsSPIP à collecter."
            return 1, "Mountains utilisé hors AFM (profilométrie, confocal, MEB…) : référence pour les autres produits de la gamme."
        if a(RE_FONCTION):
            return 3, f"{grp} utilisé sur une analyse que MountainsSPIP couvre : à comparer, argumentaire de remplacement."
        if a(RE_ML) and a(RE_ML_AFM):
            return 3, f"{grp} et apprentissage automatique sur des données AFM : piste de fonctionnalité à comparer."
        return 1, f"Usage courant de {grp}, sans analyse que MountainsSPIP met en avant : simple suivi de la concurrence."

    if cat == "sorties":
        if it["source"] in ("GitHub", "SourceForge"):
            v = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", it["title"])
            correctif = v and v.group(3) not in (None, "0")
            if correctif:
                return 2, f"Version corrective de {grp} : rien d'urgent, juste noter le rythme de sortie."
            return 3, f"Nouvelle version de {grp} : lire les nouveautés, comparer avec MountainsSPIP, vérifier les formats de fichiers."
        if a(RE_FINANCE):
            return 1, "Information financière : peu d'impact produit."
        if a(RE_LOGICIEL) and ("annonce" in tags or a(r"version|update|release|mise à jour")):
            return 4, f"{grp} annonce du nouveau côté logiciel : à confronter à la feuille de route MountainsSPIP."
        return 2, f"On parle de {grp} : à vérifier s'il y a une nouveauté fonctionnelle."

    if cat == "constructeurs":
        if grp == "Digital Surf":
            return 3, "On parle de Digital Surf : à relayer ou à surveiller."
        if a(RE_FINANCE):
            return 1, "Information financière ou étude de marché : peu d'impact produit."
        if a(RE_STRATEGIE):
            return 4, f"Mouvement stratégique chez {grp} : impact possible sur le partenariat et la distribution."
        annonce = "annonce" in tags
        if annonce and a(RE_LOGICIEL):
            return 4, f"{grp} avance côté logiciel ou analyse : à confronter à la feuille de route MountainsSPIP."
        if annonce and a(RE_MATERIEL):
            return 3, f"Nouveau matériel ou mode chez {grp} : vérifier l'import des fichiers et les fonctions d'analyse associées."
        return 2, f"Actualité {grp} : contexte marché."

    # littérature
    if a(RE_ML) and a(RE_FONCTION):
        return 3, "Méthode d'analyse automatisée sur un sujet MountainsSPIP : piste de fonctionnalité."
    if a(RE_FONCTION) or majeure:
        return 2, "Tendance scientifique sur une analyse couverte par Mountains : veille de fond utile."
    return 1, "Veille scientifique générale."


# ---------------------------------------------------------------- anti-bruit
# « SPIP » est aussi un acronyme indonésien (contrôle interne de l'État) : on exige un vrai contexte AFM.
RE_CTX_SPIP = (r"\bafm\b|atomic force|scanning probe|image metrology|spip software|nanoindent|kelvin probe|"
               r"\bkpfm\b|cantilever|force spectroscopy|scanning tunnel")
# « Park Systems » ramène des parcs publics : on garde la société, pas les parcs.
RE_PARCS = r"(state|national|regional|city|county|solar|wind|energy|public|theme)\s+park systems"


def pertinent(it, texte_complet=""):
    """Faux si l'élément est un faux positif évident (à supprimer)."""
    t = (it["title"] + " " + it.get("abstract", "") + " " + (texte_complet or "")).lower()
    if it["cat"] == "logiciels" and it["group"].startswith("SPIP"):
        return re.search(RE_CTX_SPIP, t) is not None
    if it["cat"] == "litterature":
        # les requêtes thématiques sont larges : on exige que l'AFM (ou le champ proche) soit vraiment là
        return re.search(RE_AFM + r"|s-snom|afm-ir|nanoir|tip-enhanced|near-field microscop|piezoresponse", t) is not None
    if it["cat"] == "sorties" and it["source"] == "Google Actualités":
        return re.search(r"software|logiciel|analysis|nanoscope|smartscan|smartanalysis|ergo|studio|release|version|ai\b", it["title"].lower()) is not None
    if it["cat"] == "constructeurs" and it["group"] != "Park Systems":
        # l'actu doit parler de la société ou de l'AFM, pas d'un article qui la cite en passant
        noms = r"bruker|oxford instruments|asylum|nanosurf|horiba|nt-mdt|digital surf|mountains"
        return re.search(noms + "|" + RE_AFM, it["title"].lower()) is not None
    if it["cat"] == "constructeurs" and it["group"] == "Park Systems":
        titre = it["title"]
        if re.search(RE_AFM + r"|microscop|nanoscien", titre.lower()):
            return True
        return "Park Systems" in titre and not re.search(RE_PARCS, titre.lower())
    return True


RE_PREPRINT = r"rxiv|research square|preprint|prépublication|ssrn|preprints\.org"


def sans_doublons(items):
    """Même article vu deux fois (prépublication puis revue, ou deux sources) : on garde le meilleur."""
    def cle_titre(i):
        return re.sub(r"[^a-z0-9]", "", i["title"].lower())[:60]

    def qualite(i):
        return (i.get("imp", 0), not re.search(RE_PREPRINT, (i.get("venue") or "").lower()),
                bool(i.get("doi")), i.get("score", 0), i.get("date", ""))
    meilleur = {}
    for i in items:
        k = cle_titre(i)
        if k not in meilleur or qualite(i) > qualite(meilleur[k]):
            if k in meilleur:  # on garde la date de première détection la plus ancienne
                i["first_seen"] = min(i["first_seen"], meilleur[k]["first_seen"])
            meilleur[k] = i
        else:
            meilleur[k]["first_seen"] = min(i["first_seen"], meilleur[k]["first_seen"])
    return list(meilleur.values())


def charger_exclusions(cfg):
    """Fiches marquées « Pas pertinent » : on les retire, et on apprend les sources et mots à éviter."""
    ex = {"ids": [], "fiches": []}
    if os.path.exists(FICHIER_EXCLUS):
        with open(FICHIER_EXCLUS, encoding="utf-8") as f:
            ex.update(json.load(f))
    ids = set(ex.get("ids", [])) | {x.get("id") for x in ex.get("fiches", [])}
    # une revue ou un média écarté deux fois est écarté pour la suite (sauf serveurs de prépublication et revues majeures)
    proteges = {r.lower() for r in cfg.get("revues_majeures", [])}
    compte = {}
    for x in ex.get("fiches", []):
        v = (x.get("venue") or "").strip().lower()
        if v and v not in proteges and not re.search(RE_PREPRINT, v):
            compte[v] = compte.get(v, 0) + 1
    venues = {v for v, n in compte.items() if n >= 2}
    mots = [m.lower() for m in cfg.get("mots_exclus", [])]
    return ids, venues, mots


def exclu(it, regles):
    ids, venues, mots = regles
    if it["id"] in ids or (it.get("venue") or "").strip().lower() in venues:
        return True
    t = it["title"].lower()
    return any(m in t for m in mots)


def dans_periode(it, date_min):
    return not date_min or not it.get("date") or it["date"] >= date_min


# ---------------------------------------------------------------- principal
def collecter(cfg, depuis, depuis_logiciels=None):
    depuis_logiciels = depuis_logiciels or depuis
    lots = []

    def essai(nom, fn, *a):
        try:
            r = fn(*a)
            print(f"  {nom} : {len(r)}")
            lots.extend(r)
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"{nom} : {e}")
            print(f"  {nom} : ERREUR {e}", file=sys.stderr)
        time.sleep(1)

    for logiciel, termes in cfg["logiciels"].items():
        req = " OR ".join(f'"{t}"' if '"' not in t and " " in t else t for t in termes)
        afm = cfg["termes_afm"]
        if logiciel == "Mountains":
            # seulement l'AFM : MountainsSPIP (toutes graphies), ou un autre Mountains cité avec un sujet AFM
            spip = " OR ".join(f'"{t}"' if " " in t else t for t in termes if "spip" in t.lower())
            autres = " OR ".join(f'"{t}"' if " " in t else t for t in termes if "spip" not in t.lower())
            req = f"{spip} OR (({autres}) AND ({afm}))"
        elif logiciel.startswith("SPIP"):
            # l'ancien SPIP (Image Metrology) : « SPIP » seul est ambigu, on exige un contexte
            req = f'"SPIP software" OR ("Image Metrology" AND SPIP) OR (SPIP AND ({afm}))'
        essai(f"OpenAlex {logiciel}", openalex_recherche, cfg, req, depuis_logiciels, "logiciels", logiciel)
        essai(f"Europe PMC {logiciel}", europepmc_recherche, cfg, req, depuis_logiciels, "logiciels", logiciel)
    for theme, req in cfg["themes_afm"].items():
        essai(f"OpenAlex {theme}", openalex_recherche, cfg, req, depuis, "litterature", theme)
    for req in cfg["arxiv"]:
        essai(f"arXiv {req[:40]}", arxiv_recherche, cfg, req, depuis)
    for nom, req in cfg["constructeurs"].items():
        essai(f"Actus {nom}", gnews, req, depuis, nom)
    # sorties logicielles des concurrents : on remonte toujours jusqu'à date_min
    ds = cfg.get("date_min") or depuis
    sl = cfg.get("sorties_logicielles", {})
    for nom, depot in sl.get("github", {}).items():
        essai(f"Versions {nom}", github_releases, depot, ds, nom)
    if sl.get("gwyddion"):
        essai("Versions Gwyddion", gwyddion_versions, ds)
    for nom, req in sl.get("actus", {}).items():
        essai(f"Annonces {nom}", gnews_sorties, req, ds, nom)
    return lots


def main():
    with open(FICHIER_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    anciens = []
    if os.path.exists(FICHIER_ITEMS):
        with open(FICHIER_ITEMS, encoding="utf-8") as f:
            anciens = json.load(f)
    meta_avant = {}
    if os.path.exists(FICHIER_META):
        with open(FICHIER_META, encoding="utf-8") as f:
            meta_avant = json.load(f)
    hors_ligne = "--nettoyer" in sys.argv  # applique filtres et notation sans rien collecter
    # nouvelles règles de recherche : on refait un passage long pour rattraper
    rattrapage = meta_avant.get("version_requetes", 1) < VERSION_REQUETES
    jours = cfg["fenetre_jours_quotidienne"] if anciens and not rattrapage else cfg["fenetre_jours_premier_passage"]
    depuis = (AUJOURDHUI - dt.timedelta(days=jours)).isoformat()
    # les mentions de logiciels sont rares : au rattrapage on remonte plus loin
    jl = cfg["fenetre_jours_logiciels_rattrapage"] if (rattrapage or not anciens) else jours
    depuis_logiciels = (AUJOURDHUI - dt.timedelta(days=jl)).isoformat()
    date_min = cfg.get("date_min", "")
    regles = charger_exclusions(cfg)
    depuis, depuis_logiciels = max(depuis, date_min), max(depuis_logiciels, date_min)
    print(f"Collecte depuis le {depuis}")

    par_id = {it["id"]: it for it in anciens}
    resumes_en = {}
    if os.path.exists(FICHIER_RESUMES_EN):
        with open(FICHIER_RESUMES_EN, encoding="utf-8") as f:
            resumes_en = json.load(f)
    nouveaux = 0
    priorite = {"citations": 0, "sorties": 1, "logiciels": 1, "constructeurs": 2, "litterature": 3}
    for it in ([] if hors_ligne else collecter(cfg, depuis, depuis_logiciels)):
        if not it["title"] or not dans_periode(it, date_min) or exclu(it, regles) or not pertinent(it, it.get("_abs", "")):
            continue
        noter(it, cfg)
        texte_complet = it.pop("_abs", "")
        if len(texte_complet) > len(resumes_en.get(it["id"], "")):
            resumes_en[it["id"]] = texte_complet
        ex = par_id.get(it["id"])
        if ex:
            # même publication trouvée par plusieurs requêtes : on garde la catégorie la plus forte
            if priorite[it["cat"]] < priorite[ex["cat"]]:
                it["first_seen"] = ex["first_seen"]
                par_id[it["id"]] = it
            else:
                ex["cited_by"] = max(ex.get("cited_by", 0), it["cited_by"])
                # accès libre : on complète ce qu'on ne savait pas encore
                if ex.get("oa") is not True and it.get("oa") is not None:
                    ex["oa"] = it["oa"]
                if not ex.get("oa_url") and it.get("oa_url"):
                    ex["oa_url"] = it["oa_url"]
                noter(ex, cfg)
            continue
        it["first_seen"] = AUJOURDHUI.isoformat()
        par_id[it["id"]] = it
        nouveaux += 1

    limite = (AUJOURDHUI - dt.timedelta(days=cfg["conservation_jours"])).isoformat()
    items = [i for i in par_id.values() if i["first_seen"] >= limite and dans_periode(i, date_min) and not exclu(i, regles)
             and pertinent(i, resumes_en.get(i["id"], ""))]
    for i in items:  # les règles évoluent : on renote tout à chaque passage
        noter(i, cfg)
    # on ne garde que l'essentiel : niveau minimal, pas de citations, pas de doublons
    items = sans_doublons([i for i in items if i["cat"] != "citations" and i["imp"] >= cfg.get("imp_min", 1)])
    items.sort(key=lambda i: (i["first_seen"], i["score"]), reverse=True)

    os.makedirs(os.path.dirname(FICHIER_ITEMS), exist_ok=True)
    with open(FICHIER_ITEMS, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=0)
    gardes = {i["id"] for i in items}
    with open(FICHIER_RESUMES_EN, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in resumes_en.items() if k in gardes and v}, f, ensure_ascii=False, indent=0)
    if hors_ligne:
        meta_avant.update({"total": len(items)})
        with open(FICHIER_META, "w", encoding="utf-8") as f:
            json.dump(meta_avant, f, ensure_ascii=False, indent=1)
        print(f"Nettoyage : {len(anciens)} -> {len(items)} éléments")
        return
    with open(FICHIER_META, "w", encoding="utf-8") as f:
        json.dump({"maj": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                   "version_requetes": VERSION_REQUETES,
                   "nouveaux": nouveaux, "total": len(items), "erreurs": erreurs},
                  f, ensure_ascii=False, indent=1)
    print(f"{nouveaux} nouveautés, {len(items)} éléments au total, {len(erreurs)} erreur(s)")


if __name__ == "__main__":
    main()
