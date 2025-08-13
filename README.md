# vent-pdf

Génère un PDF avec cartouche météo (Open‑Meteo, sans clé) toutes les 5 minutes via GitHub Actions.

## Usage local
```bash
python inject_wind_to_pdf_openmeteo.py --ville "Reims" --input mon_document.pdf --output mon_document_cartouche.pdf --w 135 --h 66 --fontsize 9 --margin 12
```
Options :
- `--compact` : libellés raccourcis (Dir / Force).
- Points cardinaux en français (O = Ouest).

## GitHub Pages
Le workflow écrit `docs/sortie.pdf`. Active **Settings → Pages → Branch: main / Folder: /docs** puis ouvre l’URL :
`https://<ton-user>.github.io/vent-pdf/sortie.pdf`
