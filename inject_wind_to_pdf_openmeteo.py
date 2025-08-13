import fitz
import requests
import argparse
from datetime import datetime

# --------------------------
# Fonction pour récupérer les données météo depuis OpenMeteo
# --------------------------
def get_wind_data(ville):
    # Coordonnées de la ville (ici Reims, à modifier si besoin)
    coords = {
        "Reims": (49.2583, 4.0317)
    }
    if ville not in coords:
        raise ValueError(f"Ville {ville} non configurée")

    lat, lon = coords[ville]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&windspeed_unit=kmh"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()

    wind_dir = data["current_weather"]["winddirection"]
    wind_speed = data["current_weather"]["windspeed"]

    # Conversion en direction cardinale simple
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    ix = round(wind_dir / 22.5) % 16
    return dirs[ix], wind_speed

# --------------------------
# Dessine le cartouche
# --------------------------
def draw_cartouche(page, text_lines, x, y, w, h, fontsize=10, fill=True):
    # Dessine un rectangle blanc
    if fill:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y, x + w, y + h))
        shape.finish(fill=(1, 1, 1))
        shape.commit()

    # Écrit chaque ligne
    text_y = y + 4
    for line in text_lines:
        page.insert_text(
            (x + w - 4, text_y),
            line,
            fontsize=fontsize,
            fontname="helv",
            color=(0, 0, 0),
            align=2  # Aligné à droite
        )
        text_y += fontsize + 2

# --------------------------
# Programme principal
# --------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ville", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--w", type=float, default=135)
    parser.add_argument("--h", type=float, default=66)
    parser.add_argument("--fontsize", type=int, default=10)
    parser.add_argument("--margin", type=int, default=12)
    parser.add_argument("--no-fill", action="store_true")
    args = parser.parse_args()

    # Récupération des données météo
    direction, force = get_wind_data(args.ville)

    # Préparation des lignes à afficher
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = [
        args.ville,
        now,
        f"Direction : {direction}",
        f"Force : {force} km/h"
    ]

    # Ouvre le PDF
    doc = fitz.open(args.input)
    page = doc[0]

    # Dimensions page
    rect = page.rect
    x = rect.width - args.w - args.margin
    y = args.margin

    draw_cartouche(
        page, lines, x, y, args.w, args.h,
        fontsize=args.fontsize, fill=not args.no_fill
    )

    # Sauvegarde
    doc.save(args.output)
    doc.close()

if __name__ == "__main__":
    main()
