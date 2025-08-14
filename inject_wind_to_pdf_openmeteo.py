#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Génère un cartouche vent (4 lignes) en haut-droite du PDF à partir des données Météo-France.

Dépendances :
  pip install meteofrance-api PyMuPDF

Notes :
- Recherche de lieu via l'API Météo-France (pas besoin de clé).
- On sélectionne l'échéance de prévision la plus proche de "maintenant".
- Vitesse affichée en km/h, direction en points cardinaux FR (O au lieu de W).
- Heure affichée = heure locale actuelle (avec secondes) pour garantir un diff à chaque run.
- Paramètre --stamp facultatif pour ajouter un micro-tampon invisible et forcer la mise à jour.

Usage (exemple) :
  python inject_wind_to_pdf_meteofrance.py \
    --ville "Reims, France" --input mon_document.pdf --output docs/sortie.pdf
"""

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import unicodedata

import fitz  # PyMuPDF
from meteofrance_api import MeteoFranceClient


# ----------------- utils texte / affichage -----------------
def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )

def deg_to_compass(deg: float) -> str:
    """Points cardinaux en FR avec O pour Ouest."""
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]


# ----------------- récupération Météo-France -----------------
def mf_search_place(query: str):
    """
    Recherche un lieu via Météo-France.
    Retourne l'objet place (lat/lon…) ou lève ValueError si rien.
    """
    client = MeteoFranceClient()
    places = client.search_places(query)
    if not places:
        raise ValueError(f"Ville introuvable (Météo-France) : {query}")
    return places[0]  # premier résultat


def mf_fetch_near_now_wind(place):
    """
    Récupère la prévision Météo-France pour un 'place' et renvoie :
      - speed_kmh (float ou None)
      - deg (float ou None)
      - tzname (ex: 'Europe/Paris')
    On prend l'échéance la plus proche de maintenant.
    """
    client = MeteoFranceClient()
    fc = client.get_forecast_for_place(place, language="fr")

    # La structure renvoie une liste de pas de temps 'fc.forecast' (dicts)
    steps = getattr(fc, "forecast", None)
    if not steps:
        return None, None, "Europe/Paris"

    now = int(time.time())
    best = min(steps, key=lambda s: abs(int(s.get("dt", now)) - now))

    # Les champs les plus courants dans l'API :
    # 'wind10m' (km/h) et 'dirwind10m' (degrés)
    speed = best.get("wind10m")
    deg = best.get("dirwind10m")

    # Tz : Europe/Paris pour la France métropolitaine ; le client expose tz dans fc.position
    tzname = "Europe/Paris"
    try:
        tzname = fc.position.get("timezone", tzname) or tzname
    except Exception:
        pass

    return (float(speed) if speed is not None else None,
            float(deg) if deg is not None else None,
            tzname)


# ----------------- rendu cartouche (manuel, fiable) -----------------
def _draw_line_right(page: fitz.Page, right_x: float, baseline_y: float,
                     text: str, fontsize: float):
    """Écrit une ligne alignée à droite en mesurant la largeur."""
    for font in ("Times-Roman", "helv"):
        try:
            w = fitz.get_text_length(text, fontname=font, fontsize=fontsize)
            page.insert_text((right_x - w, baseline_y), text,
                             fontname=font, fontsize=fontsize, color=(0,0,0))
            return
        except Exception:
            continue
    # ultime repli
    page.insert_text((right_x - 200, baseline_y), text, fontsize=fontsize, color=(0,0,0))


def draw_cartouche(page: fitz.Page, x: float, y: float, w: float, h: float,
                   lines, title_fontsize: float, body_fontsize: float,
                   fill: bool = True, micro_stamp: str | None = None):
    """Cadre gris + fond blanc + 4 lignes (ville plus grande)."""
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1,1,1) if fill else None, width=0.5)
    shape.commit()

    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # Ville (titre)
    line_h_title = title_fontsize + 5.0
    _draw_line_right(page, inner.x1, inner.y0 + title_fontsize, lines[0], title_fontsize)

    # Lignes 2..4
    line_h_body = body_fontsize + 5.0
    baseline = inner.y0 + line_h_title + body_fontsize
    for txt in lines[1:]:
        _draw_line_right(page, inner.x1, baseline, txt, body_fontsize)
        baseline += line_h_body

    # Micro-stamp quasi invisible pour forcer un diff binaire (optionnel)
    if micro_stamp:
        try:
            page.insert_text((inner.x0 + 1, inner.y1 - 1.5),
                             micro_stamp, fontname="helv", fontsize=1.5, color=(0.85,0.85,0.85))
        except Exception:
            pass


# ----------------- programme principal -----------------
def main():
    ap = argparse.ArgumentParser(description="Cartouche vent Météo-France en haut-droite du PDF.")
    ap.add_argument("--ville", required=True, help='Ex.: "Reims, France" ou "Epernay, France"')
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=74.0)
    ap.add_argument("--fontsize", type=float, default=12.0)       # corps
    ap.add_argument("--title-fontsize", type=float, default=14.0) # ville
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--stamp", default=None, help="Chaîne unique pour forcer un diff (ex: RUN_ID)")
    args = ap.parse_args()

    # 1) Lieu Météo-France
    place = mf_search_place(args.ville)
    ville_name = getattr(place, "name", None) or args.ville
    # on enlève les accents de la 1re ligne pour un alignement parfaitement stable
    ville_affichee = strip_accents(ville_name)

    # 2) Vent proche de "maintenant"
    speed_kmh, deg, tzname = mf_fetch_near_now_wind(place)

    # 3) Heure locale ACTUELLE (avec secondes) pour garantir un diff
    try:
        date_txt = datetime.now(ZoneInfo(tzname or "Europe/Paris")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        date_txt = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")

    direction = deg_to_compass(deg) if deg is not None else "N/A"
    vitesse = f"{speed_kmh:.1f} km/h" if speed_kmh is not None else "N/A"

    lines = [ville_affichee, date_txt, f"Direction : {direction}", f"Vitesse : {vitesse}"]
    print("DEBUG (MF) lines_injected =", lines)

    # 4) Écriture PDF
    doc = fitz.open(args.input)
    try:
        page = doc[0]
        pr = page.rect
        x = pr.x1 - args.w - args.margin
        y = pr.y0 + args.margin
        draw_cartouche(page, x, y, args.w, args.h, lines,
                       title_fontsize=args.title_fontsize,
                       body_fontsize=args.fontsize,
                       fill=not args.no_fill,
                       micro_stamp=args.stamp)
        doc.save(args.output)
        print(f"OK (Météo-France). PDF généré : {args.output}")
    finally:
        doc.close()


if __name__ == "__main__":
    main()
