#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cartouche météo (4 lignes) en haut-droite d'un PDF – compatible GitHub Actions.
- Texte noir, écrit ligne par ligne, aligné à droite
- Police native ('helv'), repli 'Times-Roman' si besoin
- Points cardinaux FR (O = Ouest)
"""

import argparse
from datetime import datetime
import requests
import fitz  # PyMuPDF

# -------- Utilitaires --------
def deg_to_compass(deg: float) -> str:
    # Points cardinaux FR (O = Ouest)
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]

def geocode_city(query: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1, "language": "fr", "format": "json"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Ville introuvable : {query}")
    top = results[0]
    return {"name": top.get("name") or query,
            "lat": top.get("latitude"),
            "lon": top.get("longitude"),
            "timezone": top.get("timezone") or "auto"}

def fetch_current_wind(lat: float, lon: float, tz: str = "auto"):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon,
              "current": "wind_speed_10m,wind_direction_10m",
              "timezone": tz if tz else "auto"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    cur = (r.json() or {}).get("current", {})
    return {"speed_kmh": cur.get("wind_speed_10m"),
            "deg": cur.get("wind_direction_10m"),
            "time": cur.get("time")}

# -------- Rendu (ligne par ligne) --------
def draw_right_aligned_text(page, x_right: float, y_top: float, lines,
                            fontsize: float = 9.0, leading: float = 3.0,
                            fontname: str = "helv"):
    """
    Écrit chaque ligne alignée à droite en mesurant la largeur du texte.
    Compatible avec PyMuPDF des runners GitHub (utilise fitz.get_text_length()).
    """
    color = (0, 0, 0)
    y = y_top + fontsize  # baseline 1re ligne
    for txt in lines:
        try:
            width = fitz.get_text_length(txt, fontname=fontname, fontsize=fontsize)
            page.insert_text((x_right - width, y), txt, fontname=fontname, fontsize=fontsize, color=color)
        except Exception:
            # Repli si 'helv' indisponible
            width = fitz.get_text_length(txt, fontname="Times-Roman", fontsize=fontsize)
            page.insert_text((x_right - width, y), txt, fontname="Times-Roman", fontsize=fontsize, color=color)
        y += fontsize + leading

def draw_cartouche(page, x: float, y: float, w: float, h: float, lines,
                   fontsize: float = 9.0, fill: bool = True):
    """Cadre fin gris, fond blanc (désactivable), texte à droite."""
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1,1,1) if fill else None, width=0.5)
    shape.commit()

    # zone interne
    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)
    draw_right_aligned_text(page, inner.x1, inner.y0, lines,
                            fontsize=fontsize, leading=3.0, fontname="helv")

# -------- Programme principal --------
def main():
    ap = argparse.ArgumentParser(description="Injecte un cartouche vent (4 lignes) en haut-droite du PDF.")
    ap.add_argument("--ville", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=66.0)
    ap.add_argument("--fontsize", type=float, default=10.0)
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--compact", action="store_true", help="Libellés raccourcis (Dir/Force)")
    ap.add_argument("--no-fill", action="store_true", help="Ne pas remplir en blanc (diagnostic)")
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
    force = f"{spd:.1f} km/h" if spd is not None else "N/A"

    if args.compact:
        l3 = f"Dir : {direction}"
        l4 = f"Force : {force}"
    else:
        l3 = f"Direction du vent : {direction}"
        l4 = f"Force du vent : {force}"

    lines = [ville, date_txt, l3, l4]
    print("DEBUG lines_injected =", lines)

    doc = fitz.open(args.input)
    try:
        page = doc[0]
        rect = page.rect
        x = rect.x1 - args.w - args.margin
        y = rect.y0 + args.margin
        draw_cartouche(page, x, y, args.w, args.h, lines,
                       fontsize=args.fontsize, fill=not args.no_fill)
        doc.save(args.output)
        print(f"OK. PDF généré : {args.output}")
    finally:
        doc.close()

if __name__ == "__main__":
    main()
