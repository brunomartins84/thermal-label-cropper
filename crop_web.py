#!/usr/bin/env python3
"""
crop_web.py — corta etiquetas de PDFs para impressora térmica.

Uso:
    python crop_web.py arquivo.pdf [opções]

Opções:
    --pages N[,N...]    Páginas a processar (padrão: todas). Ex: --pages 1,3
    --margin MM         Margem ao redor do recorte em mm (padrão: 2)
    --gap MM            Vão mínimo entre blocos em mm (padrão: 5)
    --bridge MM         Pontes finas ignoradas em mm (padrão: 1.5)
    --threshold N       Limiar de brilho do pixel (padrão: 245)
    --sort-by-size      Ordena blocos do maior pro menor em vez de posição
    --dry-run           Mostra blocos detectados sem salvar arquivos
"""

import sys
import argparse
from pathlib import Path
import fitz
from detector import detect_regions, rect_mm
from app import run_manual

MAX_SINGLE_AREA_RATIO = 0.85


def parse_args():
    p = argparse.ArgumentParser(
        description="Corta etiquetas de PDFs para impressora térmica.",
        add_help=False,
    )
    p.add_argument("pdf", nargs="+", help="Arquivo(s) PDF de entrada")
    p.add_argument("--pages", help="Páginas a processar (ex: 1,3). Padrão: todas")
    p.add_argument("--margin", type=float, default=2, metavar="MM")
    p.add_argument("--gap", type=float, default=5, metavar="MM")
    p.add_argument("--bridge", type=float, default=1.5, metavar="MM")
    p.add_argument("--threshold", type=int, default=245, metavar="N")
    p.add_argument("--sort-by-size", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-h", "--help", action="help")
    return p.parse_args()


def save_crop(pdf_path, doc, page_num, rect, suffix, dry_run=False):
    w_mm, h_mm = rect_mm(rect)
    stem = pdf_path.stem if page_num == 0 else f"{pdf_path.stem}-p{page_num+1}"
    out_file = pdf_path.with_name(f"{stem}-{suffix}.pdf")
    if dry_run:
        print(f"  [dry-run] {suffix}: {w_mm:.0f}×{h_mm:.0f} mm → {out_file.name}")
        return out_file
    out = fitz.open()
    new_page = out.new_page(width=rect.width, height=rect.height)
    new_page.show_pdf_page(new_page.rect, doc, page_num, clip=rect)
    out.save(out_file)
    out.close()
    print(f"  ✓ {suffix}: {w_mm:.0f}×{h_mm:.0f} mm → {out_file.name}")
    return out_file


def process_page(pdf_path, doc, page_num, page, args):
    print(f"\n── Página {page_num + 1} ──")
    regions = detect_regions(
        page,
        threshold=args.threshold,
        min_gap_mm=args.gap,
        max_bridge_mm=args.bridge,
        margin_mm=args.margin,
    )
    print(f"  {len(regions)} bloco(s) encontrado(s)")

    if args.sort_by_size:
        regions.sort(key=lambda r: r.width * r.height, reverse=True)

    if args.dry_run:
        for i, r in enumerate(regions, 1):
            w_mm, h_mm = rect_mm(r)
            print(f"  bloco {i}: {w_mm:.0f}×{h_mm:.0f} mm")
        return

    page_area = page.rect.width * page.rect.height

    if len(regions) >= 2:
        for i, rect in enumerate(regions, 1):
            save_crop(pdf_path, doc, page_num, rect, f"bloco{i}", args.dry_run)
        return

    if len(regions) == 1:
        rect = regions[0]
        ratio = (rect.width * rect.height) / page_area if page_area else 1
        print(f"  bloco único ocupa {ratio:.0%} da página (limite: {MAX_SINGLE_AREA_RATIO:.0%})")
        if ratio <= MAX_SINGLE_AREA_RATIO:
            save_crop(pdf_path, doc, page_num, rect, "auto", args.dry_run)
            return

    print("  Detecção não ficou confiável. Abrindo modo manual...")
    run_manual(pdf_path, doc, page, page_num, regions)


def main():
    args = parse_args()
    for pdf_arg in args.pdf:
        pdf_path = Path(pdf_arg).expanduser()
        if not pdf_path.exists():
            print(f"Erro: arquivo não encontrado: {pdf_path}")
            continue

        doc = fitz.open(pdf_path)
        total = len(doc)

        if args.pages:
            page_nums = [int(p) - 1 for p in args.pages.split(",")]
            invalid = [n + 1 for n in page_nums if not (0 <= n < total)]
            if invalid:
                print(f"Erro: páginas inválidas: {invalid} (total: {total})")
                continue
        else:
            page_nums = list(range(total))

        for page_num in page_nums:
            process_page(pdf_path, doc, page_num, doc[page_num], args)


if __name__ == "__main__":
    main()
