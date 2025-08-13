#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ajoute un cartouche météo harmonisé en haut à droite d'un PDF existant.
- Texte noir, gras, aligné à droite
- Points cardinaux FR (O = Ouest)
- Mode normal (4 lignes) ou --compact (libellés raccourcis)

Lignes (mode normal) :
  1) Ville
  2) JJ/MM/AAAA HH:MM
  3) Direction du vent : <DIR_FR>
  4) Force du vent : <V km/h>

Exemple local :
  python inject_wind_to_pdf_openmeteo.py --ville "Reims" --input mon_document.pdf --output mon_document_cartouche.pdf --w 135 --h 66 --fontsize 9 --margin 12
"""

import argparse
from datetime import datetime
import requests
import fitz  # PyMuPDF


# --------- Utilitaires ---------
def deg_to_compass(deg: float) -> str:
    """Convertit des degrés en points cardinaux FR (O = Ouest)."""
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]


def geocode_city(query: str):
    """Géocodage via l'API Open-Meteo (nom -> lat/lon + timezone)."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1, "language": "fr", "format": "json"}, timeout=12)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Ville introuvable : {query}")
    top = results[0]
    return {
        "name": top.get("name") or query,
        "country": top.get("country_code") or "",
        "lat": top.get("latitude"),
        "lon": top.get("longitude"),
        "timezone": top.get("timezone"),
    }


def fetch_current_wind(lat: float, lon: float, tz: str = "auto"):
    """Récupère vent actuel (km/h et direction en degrés) + horodatage local."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "wind_speed_10m,wind_direction_10m",
        "timezone": tz if tz else "auto",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    current = data.get("current", {})
    return {
        "speed_kmh": current.get("wind_speed_10m"),
        "deg": current.get("wind_direction_10m"),
        "time": current.get("time"),
    }


# --------- Rendu du cartouche ---------
def draw_cartouche(page: fitz.Page, text: str, x: float, y: float, w: float, h: float,
                   fontsize: float = 9.0):
    """Dessine un cadre fin gris clair + fond blanc doux, et insère le texte noir, gras, aligné à droite."""
    border_grey = (0.75, 0.75, 0.75)  # contour
    fill_white  = (1, 1, 1)           # fond
    text_black  = (0, 0, 0)           # texte noir

    rect = fitz.Rect(x, y, x + w, y + h)
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border_grey, fill=fill_white, width=0.5)
    shape.commit()

    # padding interne
    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # texte multi-lignes aligné à droite, gras (helvb = Helvetica Bold)
    page.insert_textbox(inner, text, fontname="helv", fontsize=fontsize, color=text_black, align=2)


# --------- Programme principal ---------
def main():
    ap = argparse.ArgumentParser(description="Cartouche vent (4 lignes) en haut à droite du PDF.")
    ap.add_argument("--ville", required=True, help='Ville (ex: "Reims")')
    ap.add_argument("--input", required=True, help="PDF d'entrée")
    ap.add_argument("--output", required=True, help="PDF de sortie")
    ap.add_argument("--w", type=float, default=135.0, help="Largeur du cartouche (points)")
    ap.add_argument("--h", type=float, default=66.0, help="Hauteur du cartouche (points)")
    ap.add_argument("--fontsize", type=float, default=9.0, help="Taille de police")
    ap.add_argument("--margin", type=float, default=12.0, help="Marge depuis les bords haut/droite (points)")
    ap.add_argument("--compact", action="store_true", help="Libellés raccourcis (Dir/Force)")
    args = ap.parse_args()

    # 1) Ville -> lat/lon + timezone
    info = geocode_city(args.ville)

    # 2) Vent actuel
    meteo = fetch_current_wind(info["lat"], info["lon"], tz=info.get("timezone"))

    # 3) Texte des 4 lignes
    ville = info["name"]

    when_iso = meteo.get("time")
    if when_iso:
        try:
            dt = datetime.fromisoformat(when_iso)
            date_complete = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_complete = when_iso
    else:
        date_complete = datetime.now().strftime("%d/%m/%Y %H:%M")

    deg = meteo.get("deg")
    direction = deg_to_compass(float(deg)) if deg is not None else "N/A"

    speed_kmh = meteo.get("speed_kmh")
    force_txt = f"{speed_kmh:.1f} km/h" if speed_kmh is not None else "N/A"

    if args.compact:
        line3 = f"Dir : {direction}"
        line4 = f"Force : {force_txt}"
    else:
        line3 = f"Direction du vent : {direction}"
        line4 = f"Force du vent : {force_txt}"

    text = f"{ville}\n{date_complete}\n{line3}\n{line4}"

    # 4) Insertion en haut-droite
    doc = fitz.open(args.input)
    try:
        page = doc[0]
        rect = page.rect
        x = rect.x1 - args.w - args.margin
        y = rect.y0 + args.margin
        draw_cartouche(page, text, x, y, args.w, args.h, fontsize=args.fontsize)
        doc.save(args.output)
        print(f"OK. PDF généré : {args.output}")
    finally:
        doc.close()


if __name__ == "__main__":
    main()
