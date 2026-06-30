# thermal-label-cropper

Automatically detects and crops shipping labels from PDFs for thermal printer printing.

## How it works

Pass a PDF file and the script detects content blocks on the page using pixel analysis (NumPy + PyMuPDF):

- **2 blocks found** → saves each as a separate PDF (`-bloco1.pdf`, `-bloco2.pdf`)
- **1 block found** → saves it as `-auto.pdf`
- **Detection fails** → opens a Flask server in the browser so you can drag a crop rectangle manually

## Requirements

```bash
pip install pymupdf numpy flask
```

## Usage

```bash
python crop_web.py your-label.pdf
```

Or use the helper script (add to your `~/bin/magic`):

```zsh
#!/bin/zsh
cd ~/Downloads/pdf-label || exit 1
source .venv/bin/activate
python crop_web.py "$1"
```

Then just run:

```bash
magic your-label.pdf
```

## Tunable parameters

| Parameter | Default | Description |
|---|---|---|
| `WHITE_THRESHOLD` | 245 | Pixel brightness below this counts as content |
| `MIN_GAP_MM` | 5 mm | Minimum whitespace gap to separate two blocks |
| `MAX_BRIDGE_MM` | 1.5 mm | Thin lines (borders, cut marks) smaller than this are ignored |
| `MAX_SINGLE_AREA_RATIO` | 0.85 | If a single block covers more than this ratio of the page, auto-detection is skipped |
| `MARGIN_MM` | 2 mm | Extra margin added around each detected crop |
