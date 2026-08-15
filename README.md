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

Or drop PDFs into `~/Downloads/pdf-label/` and use the `magic` helper (see below).

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
| `--clean` | off | Delete generated crops, keep originals |
| `--clean-all` | off | Delete all PDFs in the folder |

A file counts as a generated crop when it ends in `-bloco<N>.pdf`, `-auto.pdf`,
`-manual.pdf`, or an 8-character hex suffix from the manual UI. Everything else is
treated as an original and left alone by `--clean`.

## magic helper

`magic` wraps the whole workflow — cropping, printing and printer recovery — so it
runs from any directory. Install it by symlinking the version tracked here:

```bash
ln -sf ~/Downloads/pdf-label/magic ~/bin/magic
```

| Command | Action |
|---|---|
| `magic` | Process all PDFs in the folder |
| `magic --dry-run` | Preview detected blocks without saving |
| `magic --print-preview` | List which crops would be printed — touches nothing |
| `magic --print` | Print the crops, one job at a time |
| `magic --fix` | Recover the printer when it goes offline |
| `magic --clean` | Delete generated crops, keep originals |
| `magic --clean-all` | Delete everything |

`--print` and `--print-preview` only ever pick up generated crops (`-bloco*`,
`-auto`, `-manual`, uuid suffix) — the original PDF you saved from the website is
never sent to the printer.

`--print` queues every crop at once and then watches the queue until it drains.
The printer re-enumerates on USB after each job, alternating between two
descriptors, so the queue's device URI goes stale between jobs; the watcher
repoints it as soon as that happens, which keeps the jobs flowing without
having to serialise them.

Crops larger than the label are rotated and shrunk by `fit_label.py` before being
sent. CUPS' own `-o fit-to-page` has no effect here — the chain ends at the
vendor's `rastertodlabel` filter and the fitting is lost — so a 202x118mm crop
would otherwise be printed clipped. It lands on 74% rotated, the same number
Preview reports for that file.

Crops that already fit are sent untouched. Enlarging them clipped the output:
the printable area is smaller than the preset's nominal 100x150mm, so a 97x129mm
crop scaled up to fill it lost its edges.

## Printer troubleshooting

The thermal printer occasionally re-enumerates on USB under a different descriptor —
alternating between `usb:///LABEL-9X20?serial=…` and
`usb://Printer/POS%20Label%20Printer?serial=…`. When that happens the queue's device
URI no longer matches the device, CUPS gets stuck on `connecting-to-device`, and the
printer shows as offline. Power-cycling the printer does not help; the URI is what
is wrong.

```bash
magic --fix
```

It detects the real URI via `lpinfo -v`, repoints the queue with `lpadmin`, and
preserves queued jobs using `cupsdisable --hold` / `cupsenable --release` — the held
job prints once the queue is corrected, so nothing needs to be re-sent.

| Flag | Effect |
|---|---|
| `--hard` | Also kill the wedged USB backend and restart cupsd (asks for sudo) |
| `--purge` | Discard the queue instead of preserving it |

Plain `--fix` runs without sudo (`lpadmin`, `cupsdisable` and `cupsenable`
authenticate locally for members of `_lpadmin`) and only escalates to `--hard` on its
own if the printer is still stuck afterwards.

The underlying cause is likely electrical: the printer sits behind a USB hub chain,
and the current spike when the thermal head fires resets the device mid-job.
Plugging it straight into the Mac, or into a powered hub, reduces how often it
happens.

## Project structure

```
crop_web.py   # CLI entry point and page processing logic
detector.py   # pixel-based block detection (no Flask dependency)
app.py        # browser fallback UI (Flask)
fit_label.py  # scales/rotates a crop onto the label before printing
magic         # zsh wrapper: crop, print, printer recovery
```
