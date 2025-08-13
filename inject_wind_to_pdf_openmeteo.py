def draw_cartouche(page: fitz.Page, text: str, x: float, y: float, w: float, h: float,
                   fontsize: float = 9.0):
    """Cadre fin + fond blanc + texte noir aligné à droite.
       Police sûre sur GitHub Actions (helv) avec repli Times-Roman si besoin.
    """
    border_grey = (0.75, 0.75, 0.75)
    fill_white  = (1, 1, 1)
    text_black  = (0, 0, 0)

    rect = fitz.Rect(x, y, x + w, y + h)

    # cadre + fond
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(color=border_grey, fill=fill_white, width=0.5)
    shape.commit()

    # zone texte avec padding
    p = 6
    inner = fitz.Rect(rect.x0 + p, rect.y0 + p, rect.x1 - p, rect.y1 - p)

    # insertion texte (aligné à droite). Essaye helv, sinon Times-Roman.
    try:
        page.insert_textbox(inner, text, fontname="helv", fontsize=fontsize, color=text_black, align=2)
    except Exception:
        page.insert_textbox(inner, text, fontname="Times-Roman", fontsize=fontsize, color=text_black, align=2)
