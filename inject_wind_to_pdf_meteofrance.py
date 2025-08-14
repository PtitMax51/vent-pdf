#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cartouche vent (4 lignes) en haut-droite d’un PDF — données Météo-France.

Dépendances :
  pip install meteofrance-api PyMuPDF

Points clés :
- Recherche du lieu via meteofrance-api (pas de clé).
- Prend l’échéance la plus proche de "maintenant".
- Vitesse en km/h, direction en points cardinaux FR (O pour Ouest).
- Heure affichée = MAINTENANT dans le fuseau local (avec secondes) -> diff garanti.
- --stamp optionnel : mini tampon “invisible” pour forcer un diff binaire si besoin.
- 1re ligne (ville) sans accents pour un alignement stable.
"""

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import unicodedata

import fitz  # PyMuPDF
from meteofrance_api import MeteoFranceClient


# --------- utilitaires texte ----------
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def deg_to_compass(deg: float) -> str:
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]


# --------- récupération Météo-France ----------
def mf_search_place(query: str):
    client = MeteoFranceClient()
    places = client.search_places(query)
    if not places:
        raise ValueError(f"Ville introuvable (Météo-France) : {query}")
    return places[0]

def mf_fetch_near_now_wind(place):
    """
    Renvoie (speed_kmh, deg, tzname) à partir de la prévision la plus proche de maintenant.
    """
    client = MeteoFranceClient()
    fc = client.get_forecast_for_place(place, language="fr")
    steps = getattr(fc, "forecast", None)
    if not steps:
        return None, None, "Europe/Paris"

    now = int(time.time())
    best = min(steps, key=lambda s: abs(int(s.get("dt", now)) - now))

    # Champs courants renvoyés par l’API MF :
    speed = best.get("wind10m")        # km/h
    deg   = best.get("dirwind10m")     # degrés
    tz    = "Europe/Paris"
    try:
        tz = fc.position.get("timezone", tz) or tz
    except Exception:
        pass

    return (float(speed) if speed is not None else None,
            float(deg)   if deg   is not None else None,
            tz)


# --------- rendu cartouche (manuel, fiable) ----------
def _draw_line_right(page: fitz.Page, right_x: float, baseline_y: float,
                     text: str, fontsize: float):
    for font in ("Times-Roman", "helv"):
        try:
            w = fitz.get_text_length(text, fontname=font, fontsize=fontsize)
            page.insert_text((right_x - w, baseline_y), text,
                             fontname=font, fontsize=fontsize, color=(0,0,0))
            return
        except Exception:
            continue
    page.insert_text((right_x - 200, baseline_y), text, fontsize=fontsize, color=(0,0,0))

def draw_cartouche(page: fitz.Page, x: float, y: float, w: float, h: float,
                   lines, title_fontsize: float, body_fontsize: float,
                   fill: bool = True, micro_stamp: str | None = None):
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1,1,1) if fill else None, width=0.5)
    shape.commit()

    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # 1) Ville (titre)
    _draw_line_right(page, inner.x1, inner.y0 + title_fontsize, lines[0], title_fontsize)

    # 2-4) Corps
    line_h = body_fontsize + 5.0
    baseline = inner.y0 + (title_fontsize + 5.0) + body_fontsize
    for txt in lines[1:]:
        _draw_line_right(page, inner.x1, baseline, txt, body_fontsize)
        baseline += line_h

    # micro-stamp “quasi invisible” pour forcer un diff si demandé
    if micro_stamp:
        try:
            page.insert_text((inner.x0 + 1, inner.y1 - 1.5),
                             micro_stamp, fontname="helv", fontsize=1.5, color=(0.85,0.85,0.85))
        except Exception:
            pass


# --------- programme principal ----------
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

    # 1) Lieu
    place = mf_search_place(args.ville)
    ville_name = getattr(place, "name", None) or args.ville
    ville_affichee = strip_accents(ville_name)  # 1re ligne sans accents

    # 2) Vent
    speed_kmh, deg, tzname = mf_fetch_near_now_wind(place)

    # 3) Heure locale ACTUELLE avec secondes
    try:
        date_txt = datetime.now(ZoneInfo(tzname or "Europe/Paris")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        date_txt = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")

    direction = deg_to_compass(deg) if deg is not None else "N/A"
    vitesse   = f"{speed_kmh:.1f} km/h" if speed_kmh is not None else "N/A"

    lines = [ville_affichee, date_txt, f"Direction : {direction}", f"Vitesse : {vitesse}"]
    print("DEBUG (MF) lines_injected =", lines)

    # 4) PDF
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
