import base64
import json
import uuid
from pathlib import Path
import fitz
from flask import Flask, request, render_template_string
from detector import detect_regions, rect_mm, get_page_image

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PDF Crop</title>
<style>
* { box-sizing: border-box; }
body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
h2 { color: #333; }
#toolbar { margin-bottom: 12px; display: flex; gap: 10px; align-items: center; }
button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
#btn-save-all { background: #2196F3; color: white; display: none; }
#btn-save-all:hover { background: #1976D2; }
#status { color: green; font-weight: bold; }
#canvas-wrap { position: relative; display: inline-block; }
canvas { border: 1px solid #ccc; cursor: crosshair; display: block; }
.detected-label {
    position: absolute;
    background: rgba(33,150,243,0.15);
    border: 2px solid #2196F3;
    pointer-events: none;
}
.detected-label span {
    position: absolute;
    top: 4px; left: 6px;
    background: #2196F3;
    color: white;
    font-size: 11px;
    padding: 1px 5px;
    border-radius: 3px;
}
</style>
</head>
<body>
<h2>Modo manual — arraste um retângulo ou salve os blocos detectados</h2>
<div id="toolbar">
  <button id="btn-save-all" onclick="saveAll()">💾 Salvar todos os blocos detectados</button>
  <span id="status"></span>
</div>
<div id="canvas-wrap">
  <canvas id="c"></canvas>
</div>
<script>
const img = new Image();
img.src = "data:image/png;base64,{{img}}";
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const status = document.getElementById("status");
const wrap = document.getElementById("canvas-wrap");
const btnSaveAll = document.getElementById("btn-save-all");
const zoom = {{zoom}};
const detected = {{detected}};

img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    if (detected.length > 0) {
        btnSaveAll.style.display = "inline-block";
        detected.forEach((r, i) => {
            const div = document.createElement("div");
            div.className = "detected-label";
            div.style.left   = (r.x0 * zoom) + "px";
            div.style.top    = (r.y0 * zoom) + "px";
            div.style.width  = ((r.x1 - r.x0) * zoom) + "px";
            div.style.height = ((r.y1 - r.y0) * zoom) + "px";
            div.innerHTML = `<span>bloco ${i+1} · ${r.w_mm}×${r.h_mm} mm</span>`;
            wrap.appendChild(div);
        });
    }
};

let sx = 0, sy = 0, ex = 0, ey = 0, dragging = false;
canvas.onmousedown = (e) => { dragging = true; sx = e.offsetX; sy = e.offsetY; };
canvas.onmousemove = (e) => {
    if (!dragging) return;
    ex = e.offsetX; ey = e.offsetY;
    ctx.drawImage(img, 0, 0);
    ctx.strokeStyle = "red";
    ctx.lineWidth = 3;
    ctx.strokeRect(sx, sy, ex - sx, ey - sy);
};
canvas.onmouseup = async (e) => {
    dragging = false;
    ex = e.offsetX; ey = e.offsetY;
    if (Math.abs(ex - sx) < 10 || Math.abs(ey - sy) < 10) return;
    await postCrop(sx / zoom, sy / zoom, ex / zoom, ey / zoom, "manual");
    ctx.drawImage(img, 0, 0);
};

async function postCrop(x1, y1, x2, y2, suffix) {
    const fd = new FormData();
    fd.append("x1", x1); fd.append("y1", y1);
    fd.append("x2", x2); fd.append("y2", y2);
    fd.append("suffix", suffix);
    const r = await fetch("/crop", { method: "POST", body: fd });
    const text = await r.text();
    status.innerText = "✓ " + text;
    return text;
}

async function saveAll() {
    btnSaveAll.disabled = true;
    btnSaveAll.textContent = "Salvando...";
    const names = [];
    for (let i = 0; i < detected.length; i++) {
        const r = detected[i];
        const name = await postCrop(r.x0, r.y0, r.x1, r.y1, `bloco${i+1}`);
        names.push(name);
    }
    btnSaveAll.textContent = "✓ Salvo";
    status.innerText = "✓ " + names.join(", ");
}
</script>
</body>
</html>
"""


def run_manual(pdf_path: Path, doc: fitz.Document, page: fitz.Page,
               page_num: int, detected_regions, preview_zoom=2):
    png, zoom = get_page_image(page, zoom=preview_zoom)
    img64 = base64.b64encode(png).decode()

    detected_json = []
    for r in detected_regions:
        w_mm, h_mm = rect_mm(r)
        detected_json.append({
            "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
            "w_mm": round(w_mm), "h_mm": round(h_mm),
        })

    flask_app = Flask(__name__)

    @flask_app.route("/")
    def index():
        return render_template_string(
            HTML,
            img=img64,
            zoom=zoom,
            detected=json.dumps(detected_json),
        )

    @flask_app.route("/crop", methods=["POST"])
    def crop():
        x1 = float(request.form["x1"])
        y1 = float(request.form["y1"])
        x2 = float(request.form["x2"])
        y2 = float(request.form["y2"])
        suffix = request.form.get("suffix") or uuid.uuid4().hex[:8]
        rect = fitz.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        stem = pdf_path.stem if page_num == 0 else f"{pdf_path.stem}-p{page_num+1}"
        out_file = pdf_path.with_name(f"{stem}-{suffix}.pdf")
        out = fitz.open()
        new_page = out.new_page(width=rect.width, height=rect.height)
        new_page.show_pdf_page(new_page.rect, doc, page_num, clip=rect)
        out.save(out_file)
        out.close()
        return out_file.name

    import webbrowser
    url = "http://127.0.0.1:5000"
    print(f"Abrindo navegador: {url}")
    webbrowser.open(url)
    flask_app.run(host="127.0.0.1", port=5000, debug=False)
