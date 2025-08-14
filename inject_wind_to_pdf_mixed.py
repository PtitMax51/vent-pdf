#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cartouche vent (4 lignes) en haut-droite — source MIXTE :
1) Open-Meteo (temps réel) prioritaire
2) Repli : Météo-France (prévision la plus proche)

Dépendances :
  pip install requests meteofrance-api PyMuPDF
"""

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import unicodedata
import requests
import fitz  # PyMuPDF
from meteofrance_api import MeteoFranceClient

# --------- mapping interne (ajoute d’autres villes si besoin) ---------
CITY_MAP = {
    "reims":   {"name": "Reims",   "lat": 49.2583, "lon": 4.0317, "tz": "Europe/Paris"},
    "epernay": {"name": "Epernay", "lat": 49.0400, "lon": 3.9600, "tz": "Europe/Paris"},
}

# --------- utils ----------
def strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def deg_to_compass(deg: float) -> str:
    arr = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    ix = int((deg / 22.5) + 0.5) % 16
    return arr[ix]

# --------- Open-Meteo (temps réel) ----------
def fetch_openmeteo_current(lat: float, lon: float, tz: str = "auto", timeout: int = 15):
    """
    Renvoie (speed_kmh, deg, iso_time) depuis l'endpoint "current".
    Retourne (None, None, None) si indisponible.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "wind_speed_10m,wind_direction_10m",
        "timezone": tz if tz else "auto",
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        cur = (r.json() or {}).get("current") or {}
        spd = cur.get("wind_speed_10m")
        deg = cur.get("wind_direction_10m")
        iso = cur.get("time")
        if spd is None or deg is None:
            return None, None, None
        return float(spd), float(deg), iso
    except Exception:
        return None, None, None

# --------- Météo-France (prévision) ----------
def mf_fetch_near_now_wind_latlon(lat: float, lon: float, timeout: int = 15, debug: bool = False):
    """
    Renvoie (speed_kmh, deg, tzname, step_epoch) depuis la prévision la plus proche de maintenant.
    Extraction tolérante : plusieurs clés possibles (+ sous-objet 'wind'), m/s->km/h si plausible.
    """
    client = MeteoFranceClient()
    fc = client.get_forecast(lat, lon, language="fr")  # par coordonnées
    steps = getattr(fc, "forecast", None)
    if not steps:
        return None, None, "Europe/Paris", None

    now = int(time.time())
    best = min(steps, key=lambda s: abs(int(s.get("dt", now)) - now))
    if debug:
        print("DEBUG MF raw step:", best)

    speed = None
    deg = None

    # Clés directes possibles
    for k in ("wind10m", "wind_speed_10m", "windspeed10m", "wind_speed", "WindSpeed"):
        if k in best and best[k] is not None:
            try:
                speed = float(best[k]); break
            except Exception:
                pass
    for k in ("dirwind10m", "wind_direction_10m", "winddir10m", "wind_direction", "WindDirection"):
        if k in best and best[k] is not None:
            try:
                deg = float(best[k]); break
            except Exception:
                pass

    # Sous-objet wind
    if (speed is None or deg is None) and isinstance(best.get("wind"), dict):
        w = best["wind"]
        if speed is None:
            for k in ("speed", "speed10m", "v"):
                if k in w and w[k] is not None:
                    try:
                        speed = float(w[k]); break
                    except Exception:
                        pass
        if deg is None:
            for k in ("dir", "direction", "d"):
                if k in w and w[k] is not None:
                    try:
                        deg = float(w[k]); break
                    except Exception:
                        pass

    # Conversion m/s -> km/h si plausible
    if speed is not None and speed < 40:
        speed = speed * 3.6

    tz = "Europe/Paris"
    try:
        tz = fc.position.get("timezone", tz) or tz
    except Exception:
        pass

    return speed, deg, tz, int(best.get("dt", now))

# --------- rendu (aligné à droite) ----------
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
                   fill: bool = True, micro_stamp: str | None = None,
                   source_tag: str | None = None, show_source: bool = False):
    border = (0.75, 0.75, 0.75)
    rect = fitz.Rect(x, y, x + w, y + h)

    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border, fill=(1,1,1) if fill else None, width=0.5)
    shape.commit()

    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # 1) Ville
    _draw_line_right(page, inner.x1, inner.y0 + title_fontsize, lines[0], title_fontsize)

    # 2..4
    line_h = body_fontsize + 5.0
    baseline = inner.y0 + (title_fontsize + 5.0) + body_fontsize
    for txt in lines[1:]:
        _draw_line_right(page, inner.x1, baseline, txt, body_fontsize)
        baseline += line_h

    # (option) petite mention source en bas-gauche
    if show_source and source_tag:
        try:
            page.insert_text((inner.x0 + 1, inner.y1 - 1.5),
                             source_tag, fontname="helv", fontsize=6.5, color=(0.4,0.4,0.4))
        except Exception:
            pass

    # micro-stamp quasi invisible (diff garanti)
    if micro_stamp:
        try:
            page.insert_text((inner.x0 + 1, inner.y1 - 3.2),
                             micro_stamp, fontname="helv", fontsize=1.5, color=(0.85,0.85,0.85))
        except Exception:
            pass

# --------- principal ----------
def main():
    ap = argparse.ArgumentParser(description="Cartouche vent mixte (Open-Meteo temps réel, repli Météo-France).")
    ap.add_argument("--ville", required=True, help='Ex.: "Reims" ou "Epernay" (mapping interne)')
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--w", type=float, default=135.0)
    ap.add_argument("--h", type=float, default=74.0)
    ap.add_argument("--fontsize", type=float, default=12.0)        # corps
    ap.add_argument("--title-fontsize", type=float, default=14.0)  # ville
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--stamp", default=None)
    ap.add_argument("--show-source", action="store_true", help="Affiche la source en petit (OMF/MF)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    key = strip_accents(args.ville).lower().strip()
    if key not in CITY_MAP:
        raise ValueError(f'Ville non supportée : "{args.ville}". Dispo : {", ".join(CITY_MAP)}')

    meta = CITY_MAP[key]
    ville = meta["name"]
    lat, lon = meta["lat"], meta["lon"]
    tzname = meta.get("tz", "Europe/Paris")

    # 1) Open-Meteo temps réel
    spd, deg, iso = fetch_openmeteo_current(lat, lon, tz=tzname)
    source = "OMF" if (spd is not None and deg is not None) else None

    # 2) Repli : Météo-France prévision la plus proche
    if spd is None or deg is None:
        spd2, deg2, tz2, step_dt = mf_fetch_near_now_wind_latlon(lat, lon, debug=args.debug)
        if spd2 is not None and deg2 is not None:
            spd, deg = spd2, deg2
            tzname = tz2 or tzname
            source = "MF"

    # Date/heure affichée = maintenant (local, avec secondes) pour refléter l’actualisation
    try:
        date_txt = datetime.now(ZoneInfo(tzname)).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        date_txt = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")

    direction = deg_to_compass(deg) if deg is not None else "N/A"
    vitesse   = f"{spd:.1f} km/h" if spd is not None else "N/A"

    lines = [ville, date_txt, f"Direction : {direction}", f"Vitesse : {vitesse}"]
    if args.debug:
        print("DEBUG lines:", lines, "| source:", source)

    # PDF
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
                       micro_stamp=args.stamp,
                       source_tag=source,
                       show_source=args.show_source)
        doc.save(args.output)
        print(f"OK (mixte). PDF généré : {args.output}")
    finally:
        doc.close()

if __name__ == "__main__":
    main()
