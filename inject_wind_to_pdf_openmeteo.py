#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import unicodedata
import requests
import fitz  # PyMuPDF


# ---------- Utilitaires ----------
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def deg_to_compass(deg: float) -> str:
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]

def geocode_city(query: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1, "language": "fr", "format": "json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Ville introuvable : {query}")
    top = results[0]
    return {"name": top.get("name") or query,
            "lat": top.get("latitude"),
            "lon": top.get("longitude"),
            "timezone": top.get("timezone") or "UTC"}

def fetch_current_wind(lat: float, lon: float, tz: str = "auto"):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon,
              "current": "wind_speed_10m,wind_direction_10m",
              "timezone": tz if tz else "auto"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    cur = (r.json() or {}).get("current", {})
    return {"speed_kmh": cur.get("wind_speed_10m"),
            "deg": cur.get("wind_direction_10m"),
            "time": cur.get("time")}


# ---------- Rendu (textbox droite + fallback manuel) ----------
def _textbox_right(page: fitz.Page, rect: fitz.Rect, text: str, fontsize: float, fontname: str = "Times-Roman") -> bool:
    try:
        n = page.insert_textbox(rect, text, fontname=fontname, fontsize=fontsize, color=(0,0,0), align=2)
        return bool(n and n > 0)
    except Exception:
        return False

def _draw_line_right(page: fitz.Page, right_x: float, baseline_y: float, text: str, fontsize: float):
    for font in ("Times-Roman", "helv"):
        try:
            w = fitz.get_text_length(text, fontname=font, fontsize=fontsize)
            page.insert_text((right_x - w, baseline_y), text, fontname=font, fontsize=fontsize, color=(0,0,0))
            return
        except Exception:
            continue
    page.insert_text((right_x - 200, baseline_y), text, fontsize=fontsize, color=(0,0,0))

def draw_cartouche(page: fitz.Page, x: float, y: float, w: float, h: float,
                   lines, title_fontsize: float, body_fontsize: float,
                   fill: bool = True, micro_stamp: str | None = None):
    """Cadre + fond + 4 lignes (ville plus grande). Ajoute un micro-stamp invisible si fourni."""
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    # cadre + fond
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1,1,1) if fill else None, width=0.5)
    shape.commit()

    # zone interne
    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # 1) Ville (sans accents pour un alignement stable)
    line_h_title = title_fontsize + 5.0
    top = inner.y0
    r = fitz.Rect(inner.x0, top, inner.x1, top + line_h_title + 3)
    if not _textbox_right(page, r, lines[0], title_fontsize, fontname="Times-Roman"):
        _draw_line_right(page, inner.x1, top + title_fontsize, lines[0], title_fontsize)

    # 2-4) Corps
    line_h_body  = body_fontsize  + 5.0
    y_cursor = r.y1
    for txt in lines[1:]:
        rline = fitz.Rect(inner.x0, y_cursor, inner.x1, y_cursor + line_h_body + 2)
        if not _textbox_right(page, rline, txt, body_fontsize, fontname="Times-Roman"):
            _draw_line_right(page, inner.x1, y_cursor + body_fontsize, txt, body_fontsize)
        y_cursor += line_h_body

    # 5) Micro-stamp quasi invisible pour forcer un diff binaire si nécessaire
    if micro_stamp:
        try:
            page.insert_text((inner.x0 + 1, inner.y1 - 1.5),
                             micro_stamp, fontname="helv", fontsize=1.5, color=(0.85,0.85,0.85))
        except Exception:
            pass


# ---------- Programme principal ----------
def main():
    ap = argparse.ArgumentParser(description="Cartouche météo (4 lignes) en haut-droite du PDF.")
    ap.add_argument("--ville", required=True, help='Ex.: "Reims, France" ou "Epernay, France"')
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=70.0)
    ap.add_argument("--fontsize", type=float, default=12.0)
    ap.add_argument("--title-fontsize", type=float, default=14.0)
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--stamp", default=None, help="Chaîne unique (ex: GITHUB_RUN_ID) pour forcer un diff")
    args = ap.parse_args()

    info = geocode_city(args.ville)
    meteo = fetch_current_wind(info["lat"], info["lon"], tz=info.get("timezone"))

    # Ville : sans accents pour éviter tout décalage
    ville = strip_accents(info.get("name") or args.ville)

    # Heure locale ACTUELLE avec SECONDES (garantit le changement à chaque run)
    try:
        date_txt = datetime.now(ZoneInfo(info.get("timezone") or "UTC")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        date_txt = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")

    deg = meteo.get("deg")
    direction = deg_to_compass(float(deg)) if deg is not None else "N/A"
    spd = meteo.get("speed_kmh")
    vitesse = f"{spd:.1f} km/h" if spd is not None else "N/A"

    lines = [ville, date_txt, f"Direction : {direction}", f"Vitesse : {vitesse}"]
    print("DEBUG lines_injected =", lines)

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
        print(f"OK. PDF généré : {args.output}")
    finally:
        doc.close()

if __name__ == "__main__":
    main()
