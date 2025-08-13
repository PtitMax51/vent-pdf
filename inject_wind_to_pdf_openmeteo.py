#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Génère un cartouche météo (4 lignes) en haut à droite d'un PDF existant.
Compatibilité GitHub Actions (polices natives de PyMuPDF).

Lignes :
  1) Ville
  2) JJ/MM/AAAA HH:MM
  3) Direction du vent : <DIR_FR>
  4) Force du vent : <V km/h>
"""

import argparse
from datetime import datetime
import requests
import fitz  # PyMuPDF

# ---------- Utilitaires ----------
def deg_to_compass(deg: float) -> str:
    """Points cardinaux FR (O = Ouest)."""
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]

def geocode_city(query: str):
    """Nom de ville -> lat/lon/timezone via Open‑Meteo (sans clé)."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1, "language": "fr", "format": "json"}, timeout=15)
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
    """Vent actuel + horodatage local."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "wind_speed_10m,wind_direction_10m",
        "timezone": tz if tz else "auto",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    cur = (r.json() or {}).get("current", {})
    return {
        "speed_kmh": cur.get("wind_speed_10m"),
        "deg": cur.get("wind_direction_10m"),
        "time": cur.get("time"),  # ISO local
    }

# ---------- Rendu ----------
def draw_cartouche(page, text: str, x: float, y: float, w: float, h: float, fontsize: float = 9.0):
    """Cadre fin + fond blanc + texte noir, aligné à droite. Police sûre ('helv'), fallback Times-Roman."""
    border_grey = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border_grey, fill=(1, 1, 1), width=0.5)
    shape.commit()

    p = 6  # padding
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    try:
        page.insert_textbox(inner, text, fontname="helv", fontsize=fontsize, color=(0, 0, 0), align=2)
    except Exception:
        # fallback si jamais 'helv' n'est pas dispo
        page.insert_textbox(inner, text, fontname="Times-Roman", fontsize=fontsize, color=(0, 0, 0), align=2)

# ---------- Programme principal ----------
def main():
    ap = argparse.ArgumentParser(description="Injecte un cartouche vent en haut-droite du PDF.")
    ap.add_argument("--ville", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=66.0)
    ap.add_argument("--fontsize", type=float, default=9.0)
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--compact", action="store_true", help="Libellés raccourcis (Dir/Force)")
    args = ap.parse_args()

    info = geocode_city(args.ville)
    meteo = fetch_current_wind(info["lat"], info["lon"], tz=info.get("timezone"))

    ville = info.get("name") or args.ville

    # Date locale avec année
    when_iso = meteo.get("time")
    if when_iso:
        try:
            dt = datetime.fromisoformat(when_iso)
            date_complete = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_complete = when_iso
    else:
        date_complete = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Direction & force
    deg = meteo.get("deg")
    direction = deg_to_compass(float(deg)) if deg is not None else "N/A"
    spd = meteo.get("speed_kmh")
    force_txt = f"{spd:.1f} km/h" if spd is not None else "N/A"

    if args.compact:
        l3 = f"Dir : {direction}"
        l4 = f"Force : {force_txt}"
    else:
        l3 = f"Direction du vent : {direction}"
        l4 = f"Force du vent : {force_txt}"

    text = f"{ville}\n{date_complete}\n{l3}\n{l4}"
    print("DEBUG text_injected =", repr(text))  # utile dans les logs Actions

    # Injection en haut-droite
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
