# thermal-label-cropper

Automatically detects and crops shipping labels from PDFs for thermal printer printing.

## How it works

Pass a PDF and the script detects content blocks using pixel analysis (NumPy + PyMuPDF):

- **2+ blocks found** → saves each as a separate PDF (`-bloco1.pdf`, `-bloco2.pdf`, …)
- **1 block found** → saves it as `-auto.pdf`
- **Detection fails** → opens a browser UI so you can see the detected blocks and drag a crop rectangle manually

Detection scans both **vertically and horizontally**, so labels placed side-by-side are handled correctly.

## Requirements

```bash
pip install pymupdf numpy flask
```

## Usage

```bash
python crop_web.py label.pdf
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--pages 1,3` | all | Process only specific pages |
| `--margin MM` | 2 mm | Extra margin around each crop |
| `--gap MM` | 5 mm | Minimum whitespace gap to separate two blocks |
| `--bridge MM` | 1.5 mm | Thin lines (borders, cut marks) smaller than this are ignored |
| `--threshold N` | 245 | Pixel brightness below this counts as content |
| `--sort-by-size` | off | Sort blocks largest-first instead of by position |
| `--dry-run` | off | Show detected blocks without saving any files |

### Examples

```bash
# Preview what would be detected without saving
python crop_web.py label.pdf --dry-run

# Only process page 1, with a bigger margin
python crop_web.py label.pdf --pages 1 --margin 4

# Sort crops largest-first
python crop_web.py label.pdf --sort-by-size
```

## Helper script

Add this to `~/bin/magic` to run from anywhere:

```zsh
#!/bin/zsh
cd ~/Downloads/pdf-label || exit 1
source .venv/bin/activate
python crop_web.py "$@"
```

Then:

```bash
magic label.pdf --dry-run
```

## Project structure

```
crop_web.py   # CLI entry point + page processing logic
detector.py   # pixel-based block detection (pure logic, no Flask)
app.py        # browser fallback UI (Flask)
```
