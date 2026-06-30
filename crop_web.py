import sys
import base64
import uuid
from pathlib import Path
import fitz
import numpy as np
from flask import Flask, request, render_template_string

if len(sys.argv) < 2:
    print("Uso: python3 crop_web.py arquivo.pdf")
    sys.exit(1)

PDF = Path(sys.argv[1]).expanduser()
doc = fitz.open(PDF)
page = doc[0]
zoom = 2

# --- parâmetros de detecção (ajustáveis) ---
DETECT_ZOOM = 3
WHITE_THRESHOLD = 245          # abaixo disso conta como "não-branco"
MIN_GAP_MM = 5                 # vão em branco mínimo pra considerar dois blocos separados
MAX_BRIDGE_MM = 1.5            # "pontes" finas (bordas de caixa, linha de corte) menores que isso são ignoradas
MAX_SINGLE_AREA_RATIO = 0.85   # se achar só 1 bloco e ele ocupar mais que isso da página, não confia
MARGIN_MM = 2                   # margem extra ao redor do recorte detectado


def mm_to_px(mm, zoom):
    return mm * 72 / 25.4 * zoom


def rect_mm(rect):
    return rect.width * 25.4 / 72, rect.height * 25.4 / 72


def remove_thin_bridges(row_has_content, max_bridge_px):
    """
    Trata faixas finas de conteúdo (borda de caixa, linha de corte tracejada)
    como se fossem espaço em branco, pra não quebrar um vão real em dois
    vãos menores que individualmente não passam do limite.
    """
    arr = row_has_content.copy()
    n = len(arr)
    i = 0
    while i < n:
        if arr[i]:
            j = i
            while j < n and arr[j]:
                j += 1
            if (j - i) <= max_bridge_px:
                arr[i:j] = False
            i = j
        else:
            i += 1
    return arr


def detect_regions(page, zoom=DETECT_ZOOM, threshold=WHITE_THRESHOLD,
                    min_gap_mm=MIN_GAP_MM, max_bridge_mm=MAX_BRIDGE_MM, margin_mm=MARGIN_MM):
    """
    Encontra blocos de conteúdo não-branco na página, separando-os por
    vãos em branco reais (ignorando bordas/linhas finas que não contam
    como separação de verdade). Retorna lista de fitz.Rect, de cima pra baixo.
    """
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = img[..., :3].mean(axis=2)
    mask = gray < threshold

    margin_px = mm_to_px(margin_mm, zoom)

    row_has_content = mask.any(axis=1)
    row_has_content = remove_thin_bridges(row_has_content, mm_to_px(max_bridge_mm, zoom))

    min_gap_px = mm_to_px(min_gap_mm, zoom)

    bands = []
    in_band = False
    gap = 0
    start = 0
    for i, has in enumerate(row_has_content):
        if has:
            if not in_band:
                start = i
                in_band = True
            gap = 0
        elif in_band:
            gap += 1
            if gap > min_gap_px:
                bands.append((start, i - gap))
                in_band = False
    if in_band:
        bands.append((start, len(row_has_content) - 1))

    regions = []
    for y0, y1 in bands:
        sub_mask = mask[y0:y1 + 1, :]
        cols = np.where(sub_mask.any(axis=0))[0]
        if len(cols) == 0:
            continue
        x0, x1 = int(cols.min()), int(cols.max())
        x0 = max(0, x0 - margin_px)
        y0m = max(0, y0 - margin_px)
        x1 = min(pix.width - 1, x1 + margin_px)
        y1m = min(pix.height - 1, y1 + margin_px)
        rect = fitz.Rect(x0 / zoom, y0m / zoom, x1 / zoom, y1m / zoom)
        regions.append(rect)

    return regions


def save_crop(rect, suffix):
    out_file = PDF.with_name(f"{PDF.stem}-{suffix}.pdf")
    out = fitz.open()
    new_page = out.new_page(width=rect.width, height=rect.height)
    new_page.show_pdf_page(new_page.rect, doc, 0, clip=rect)
    out.save(out_file)
    out.close()
    return out_file


# --- 1) Detecção automática ---
regions = detect_regions(page)
print(f"[debug] {len(regions)} bloco(s) de conteúdo encontrados")

auto_ok = False

if len(regions) == 2:
    auto_ok = True
    for i, rect in enumerate(regions, start=1):
        w_mm, h_mm = rect_mm(rect)
        out_file = save_crop(rect, f"bloco{i}")
        print(f"✓ bloco {i}: {w_mm:.0f} x {h_mm:.0f} mm -> {out_file.name}")

elif len(regions) == 1:
    rect = regions[0]
    page_area = page.rect.width * page.rect.height
    ratio = (rect.width * rect.height) / page_area if page_area else 1
    print(f"[debug] bloco único ocupa {ratio:.0%} da página (limite: {MAX_SINGLE_AREA_RATIO:.0%})")
    if ratio <= MAX_SINGLE_AREA_RATIO:
        auto_ok = True
        out_file = save_crop(rect, "auto")
        print(f"✓ etiqueta: {out_file.name}")

else:
    print(f"[debug] número de blocos inesperado ({len(regions)})")

if auto_ok:
    sys.exit(0)

print("Detecção automática não ficou confiável. Abrindo modo manual...")

# --- 2) Fallback: modo manual no navegador ---
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
png = pix.tobytes("png")
img64 = base64.b64encode(png).decode()

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PDF Crop</title>
<style>
body { font-family: sans-serif; margin: 20px; }
canvas { border: 1px solid #ccc; cursor: crosshair; }
#status { margin-bottom: 15px; color: green; font-weight: bold; }
</style>
</head>
<body>
<h2>Detecção automática falhou — arraste um retângulo em volta da área desejada</h2>
<div id="status"></div>
<canvas id="c"></canvas>
<script>
const img = new Image();
img.src = "data:image/png;base64,{{img}}";
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const status = document.getElementById("status");
let sx = 0, sy = 0, ex = 0, ey = 0, dragging = false;
img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
};
canvas.onmousedown = (e) => { dragging = true; sx = e.offsetX; sy = e.offsetY; };
canvas.onmousemove = (e) => {
    if (!dragging) return;
    ex = e.offsetX; ey = e.offsetY;
    ctx.drawImage(img, 0, 0);
    ctx.strokeStyle = "red";
    ctx.lineWidth = 4;
    ctx.strokeRect(sx, sy, ex - sx, ey - sy);
};
canvas.onmouseup = async (e) => {
    dragging = false;
    ex = e.offsetX; ey = e.offsetY;
    const formData = new FormData();
    formData.append("x1", sx);
    formData.append("y1", sy);
    formData.append("x2", ex);
    formData.append("y2", ey);
    try {
        const response = await fetch("/", { method: "POST", body: formData });
        const text = await response.text();
        status.innerText = "✓ " + text;
        ctx.drawImage(img, 0, 0);
    } catch (err) {
        console.error(err);
        status.innerText = "Erro ao gerar PDF";
    }
};
</script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML, img=img64)


@app.route("/", methods=["POST"])
def crop():
    x1 = float(request.form["x1"]) / zoom
    y1 = float(request.form["y1"]) / zoom
    x2 = float(request.form["x2"]) / zoom
    y2 = float(request.form["y2"]) / zoom
    rect = fitz.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    out_file = save_crop(rect, uuid.uuid4().hex[:8])
    return out_file.name


if __name__ == "__main__":
    print("Abra no navegador:")
    print("http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
