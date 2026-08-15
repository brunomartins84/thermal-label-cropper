#!/usr/bin/env python3
"""
fit_label.py — encaixa um recorte na etiqueta antes de imprimir.

O -o fit-to-page do CUPS nao tem efeito nesta impressora: a cadeia de filtros
vai pro rastertodlabel do fabricante e o encaixe se perde. Sem isso o lp manda
a pagina no tamanho original e o que passa da etiqueta sai cortado.

Reproduz o que o Preview faz no Cmd+P: Auto Rotate + Scale to Fit, ou seja,
gira 90 graus quando isso permite uma escala maior, e centraliza.

Uso:
    python fit_label.py entrada.pdf saida.pdf [--media LARGURAxALTURA]
"""

import sys
import argparse
import fitz

MM = 72.0 / 25.4


def fit_page(src_doc, page_num, media_w, media_h):
    """Retorna (rect de destino, angulo) que maximiza a escala."""
    src = src_doc[page_num].rect
    best = None
    for angle in (0, 90):
        w, h = (src.width, src.height) if angle == 0 else (src.height, src.width)
        scale = min(media_w / w, media_h / h)
        if best is None or scale > best[0]:
            best = (scale, angle, w * scale, h * scale)

    scale, angle, out_w, out_h = best
    x = (media_w - out_w) / 2
    y = (media_h - out_h) / 2
    return fitz.Rect(x, y, x + out_w, y + out_h), angle, scale


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--media", default="100x150",
                   help="Tamanho da etiqueta em mm (padrao: 100x150)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    try:
        mw, mh = (float(v) for v in args.media.lower().split("x"))
    except ValueError:
        print(f"Erro: --media invalido: {args.media}", file=sys.stderr)
        return 1

    media_w, media_h = mw * MM, mh * MM

    src = fitz.open(args.src)
    out = fitz.open()
    for page_num in range(len(src)):
        rect, angle, scale = fit_page(src, page_num, media_w, media_h)
        page = out.new_page(width=media_w, height=media_h)
        page.show_pdf_page(rect, src, page_num, rotate=angle)
        if not args.quiet:
            print(f"  {scale:.0%}, girado {angle}graus" if angle
                  else f"  {scale:.0%}, sem giro")
    out.save(args.dst)
    out.close()
    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
