#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cartouche météo (4 lignes) en haut-droite d’un PDF.
- Données : Open-Meteo (sans clé)
- Police native ('helv'), repli 'Times-Roman'
- Alignement à droite SANS utiliser 'align' (calcul de largeur)
- Libellés : "Direction" et "Force"
"""

import argparse
from datetime import datetime
import requests
import fitz  # PyMuPDF


# ---------- Utilitaires ----------
def deg_to_compass(deg: float) -> str:
    """Direction cardinale FR (O pour Ouest)."""
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]


def geocode_city(query: str):
    """Nom de ville -> lat/lon/timezone via Open-Meteo."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1, "language": "fr", "format": "json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Ville introuvable : {query}")
    top = results[0]
    return {
        "name": top.get("name") or query,
        "lat": top.get("latitude"),
        "lon": top.get("longitude"),
        "timezone": top.get("timezone") or "auto",
    }


def fetch_current_wind(lat: float, lon: float, tz: str = "auto"):
    """Vent actuel (km/h + direction) + horodatage local."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "wind_speed_10m,wind_direction_10m",
        "timezone": tz if tz else "auto",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    cur = (r.json() or {}).get("current", {})
    return {
        "speed_kmh": cur.get("wind_speed_10m"),
        "deg": cur.get("wind_direction_10m"),
        "time": cur.get("time"),  # ISO local
    }


# ---------- Rendu : écriture à droite sans 'align' ----------
def _draw_line_right(page, right_x: float, baseline_y: float, text: str, fontsize: float):
    """Écrit une ligne alignée à droite en mesurant sa largeur."""
    for font in ("helv", "Times-Roman"):  # police de secours
        try:
            width = fitz.get_text_length(text, fontname=font, fontsize=fontsize)
            page.insert_text((right_x - width, baseline_y), text,
                             fontname=font, fontsize=fontsize, color=(0, 0, 0))
            return
        except Exception:
            continue
    # Dernier recours : écriture sans police spécifiée (gauche)
    page.insert_text((right_x - 200, baseline_y), text, fontsize=fontsize, color=(0, 0, 0))


def draw_cartouche(page, x: float, y: float, w: float, h: float, lines, fontsize: float = 10.0, fill: bool = True):
    """Cadre gris + fond optionnel + 4 lignes alignées à droite (manuel)."""
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    # Cadre + fond
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1, 1, 1) if fill else None, width=0.5)
    shape.commit()

    # Zone interne (padding)
    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # Écriture ligne par ligne (droite)
    baseline = inner.y0 + fontsize
    leading = 3.0
    for line in lines:
        _draw_line_right(page, inner.x1, baseline, line, fontsize)
        baseline += fontsize + leading


# ---------- Programme principal ----------
def main():
    ap = argparse.ArgumentParser(description="Injecte un cartouche vent (4 lignes) en haut-droite du PDF.")
    ap.add_argument("--ville", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=66.0)
    ap.add_argument("--fontsize", type=float, default=10.0)
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--no-fill", action="store_true", help="Sans fond blanc (diagnostic)")
    args = ap.parse_args()

    info = geocode_city(args.ville)
    meteo = fetch_current_wind(info["lat"], info["lon"], tz=info.get("timezone"))

    ville = info.get("name") or args.ville

    # Date locale avec année
    when_iso = meteo.get("time")
    if when_iso:
        try:
            dt = datetime.fromisoformat(when_iso)
            date_txt = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_txt = when_iso
    else:
        date_txt = datetime.now().strftime("%d/%m/%Y %H:%M")

    deg = meteo.get("deg")
    direction = deg_to_compass(float(deg)) if deg is not None else "N/A"
    spd = meteo.get("speed_kmh")
    force_txt = f"{spd:.1f} km/h" if spd is not None else "N/A"

    # Lignes finales (avec "Direction")
    lines = [
        ville,
        date_txt,
        f"Direction : {direction}",
        f"Force : {force_txt}",
    ]
    print("DEBUG lines_injected =", lines)

    # Ouverture & rendu
    doc = fitz.open(args.input)
    try:
        page = doc[0]
        page_rect = page.rect
        x = page_rect.x1 - args.w - args.margin
        y = page_rect.y0 + args.margin
        draw_cartouche(page, x, y, args.w, args.h, lines, fontsize=args.fontsize, fill=not args.no_fill)
        doc.save(args.output)
        print(f"OK. PDF généré : {args.output}")
    finally:
        doc.close()


if __name__ == "__main__":
    main()
