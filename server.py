#!/usr/bin/env python3
"""
server.py — recorta etiquetas pela web, pra imprimir do celular.

Mesma deteccao do crop_web.py, sem depender do Mac: voce abre a pagina no
celular, escolhe o PDF que baixou da transportadora, e recebe os recortes
prontos pra abrir no app de impressao Bluetooth.

    pip install pymupdf numpy flask gunicorn
    gunicorn -w 2 -b 127.0.0.1:8000 server:app
"""

import io
import re
import secrets
import shutil
import time
from pathlib import Path

import fitz
from flask import Flask, request, send_file, abort, render_template_string

from detector import detect_regions, rect_mm

MAX_UPLOAD = 25 * 1024 * 1024
MAX_PAGES = 20
SESSION_TTL = 2 * 60 * 60          # recortes somem depois de 2h
WORK_DIR = Path("/tmp/pdf-label-web")
MAX_SINGLE_AREA_RATIO = 0.85       # igual ao crop_web.py
TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD

PAGE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recortar etiqueta</title>
<style>
  :root { color-scheme: light dark; --fg:#111; --bg:#fff; --mut:#666; --line:#ddd; --acc:#2196F3; }
  @media (prefers-color-scheme: dark) {
    :root { --fg:#eee; --bg:#1c1c1e; --mut:#999; --line:#3a3a3c; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; font:16px/1.5 -apple-system,system-ui,sans-serif;
         color:var(--fg); background:var(--bg); }
  main { max-width: 32rem; margin: 0 auto; }
  h1 { font-size:1.3rem; margin:0 0 .25rem; }
  p.sub { color:var(--mut); margin:0 0 1.5rem; }
  input[type=file] { width:100%; padding:14px; border:1px dashed var(--line);
                     border-radius:10px; background:transparent; color:var(--fg); }
  button { width:100%; margin-top:14px; padding:15px; font-size:1rem; font-weight:600;
           border:0; border-radius:10px; background:var(--acc); color:#fff; }
  button:disabled { opacity:.5; }
  ul { list-style:none; padding:0; margin:1.5rem 0 0; }
  li { border:1px solid var(--line); border-radius:10px; margin-bottom:10px; }
  li a { display:block; padding:14px; text-decoration:none; color:var(--fg); }
  li a b { display:block; font-size:.95rem; word-break:break-all; }
  li a span { color:var(--mut); font-size:.85rem; }
  .warn { padding:12px 14px; border-radius:10px; border:1px solid var(--line);
          color:var(--mut); font-size:.9rem; }
  .again { display:block; text-align:center; margin-top:1.5rem; color:var(--acc); }
</style>
</head>
<body><main>
<h1>Recortar etiqueta</h1>
<p class="sub">{{ sub }}</p>

{% if not crops %}
<form method="post" action="/crop" enctype="multipart/form-data"
      onsubmit="this.querySelector('button').disabled=true;
                this.querySelector('button').textContent='Recortando...'">
  <input type="file" name="pdf" accept="application/pdf,.pdf" required>
  <button type="submit">Recortar</button>
</form>
{% else %}
  {% if warning %}<p class="warn">{{ warning }}</p>{% endif %}
  <ul>
  {% for c in crops %}
    <li><a href="{{ c.url }}" download><b>{{ c.name }}</b>
        <span>{{ c.w }}x{{ c.h }} mm</span></a></li>
  {% endfor %}
  </ul>
  <a class="again" href="/">Recortar outro</a>
{% endif %}
</main></body></html>"""


def sweep_old():
    """Remove sessoes vencidas. Roda a cada requisicao: sem cron, sem estado."""
    if not WORK_DIR.exists():
        return
    cutoff = time.time() - SESSION_TTL
    for d in WORK_DIR.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def safe_stem(name):
    stem = Path(name or "etiqueta").stem
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", stem).strip("-.") or "etiqueta"
    return stem[:60]


@app.get("/")
def index():
    sweep_old()
    return render_template_string(
        PAGE, crops=None, warning=None,
        sub="Escolha o PDF da transportadora. Os recortes saem no tamanho da etiqueta.")


@app.post("/crop")
def crop():
    sweep_old()

    up = request.files.get("pdf")
    if not up or not up.filename:
        abort(400, "Nenhum arquivo enviado.")

    raw = up.read()
    if not raw.startswith(b"%PDF"):
        abort(400, "Isso nao e' um PDF.")

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        abort(400, "Nao consegui abrir esse PDF.")

    if len(doc) > MAX_PAGES:
        abort(400, f"PDF com paginas demais (limite {MAX_PAGES}).")

    token = secrets.token_hex(8)
    out_dir = WORK_DIR / token
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = safe_stem(up.filename)
    crops, warning = [], None

    for page_num in range(len(doc)):
        page = doc[page_num]
        regions = detect_regions(page)
        prefix = stem if page_num == 0 else f"{stem}-p{page_num + 1}"

        if len(regions) == 1:
            page_area = page.rect.width * page.rect.height
            r = regions[0]
            ratio = (r.width * r.height) / page_area if page_area else 1
            if ratio > MAX_SINGLE_AREA_RATIO:
                # Sem modo manual aqui: entrega a pagina inteira e avisa.
                regions = []
                warning = ("A deteccao nao ficou confiavel nessa pagina, entao "
                           "mandei ela inteira. Se sair errado, recorte no Mac.")
                name = f"{prefix}-pagina.pdf"
                _save(doc, page_num, page.rect, out_dir / name)
                crops.append(_entry(token, name, page.rect))

        for i, rect in enumerate(regions, 1):
            suffix = f"bloco{i}" if len(regions) >= 2 else "auto"
            name = f"{prefix}-{suffix}.pdf"
            _save(doc, page_num, rect, out_dir / name)
            crops.append(_entry(token, name, rect))

    doc.close()

    if not crops:
        shutil.rmtree(out_dir, ignore_errors=True)
        abort(400, "Nao encontrei nenhum bloco nesse PDF.")

    return render_template_string(
        PAGE, crops=crops, warning=warning,
        sub=f"{len(crops)} recorte(s). Toque pra baixar e imprimir.")


def _save(doc, page_num, rect, path):
    out = fitz.open()
    page = out.new_page(width=rect.width, height=rect.height)
    page.show_pdf_page(page.rect, doc, page_num, clip=rect)
    out.save(path)
    out.close()


def _entry(token, name, rect):
    w, h = rect_mm(rect)
    return {"name": name, "url": f"/d/{token}/{name}", "w": round(w), "h": round(h)}


@app.get("/d/<token>/<name>")
def download(token, name):
    if not TOKEN_RE.match(token) or "/" in name or name != Path(name).name:
        abort(404)
    path = WORK_DIR / token / name
    if not path.is_file():
        abort(404, "Esse recorte expirou. Envie o PDF de novo.")
    return send_file(path, mimetype="application/pdf",
                     as_attachment=True, download_name=name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
