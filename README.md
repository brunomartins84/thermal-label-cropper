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
| `--pending` | off | Process only originals that have no crops yet |

`--pending` matches crops against the whole original name, not just its prefix,
so `Etiqueta-2-bloco1.pdf` is not mistaken for a crop of `Etiqueta.pdf` and the
latter still gets processed.

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
| `magic` | Crop the originals that have no crops yet, and refresh the printer's label geometry |
| `magic file.pdf` | Crop that file specifically, even if already done |
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

`--fix` also rewrites the label geometry on the printer itself. This is a TSPL
printer, so `SIZE` and `GAP` live in its own memory rather than on the Mac, and
they are lost when it sits unplugged for a few weeks. The printer then prints
into a smaller area: output is clipped and two jobs land on the same label,
while everything on the Mac still checks out — which is exactly what made it so
hard to place in Oct 2026. Rewriting them only stores settings, so it costs no
label and runs on every `--fix`, including when nothing else needed fixing. The
values come from `LABEL_SIZE_MM` / `LABEL_GAP_MM` at the top of the script;
change them if the roll changes.

If output is still misaligned afterwards, the next step is the `GAPDETECT`
command, which measures the gap itself and consumes a couple of labels.

Plain `magic` rewrites them too, but only when it actually produced crops —
that is, right before a print session. There are two identical printers sharing
the same factory serial, so there is no way to tell which one is plugged in or
how long it sat without power; rewriting costs a few seconds, no label, and
removes the chance of finding out from a clipped print. It is skipped when a
job is already pending, so nothing piles up while a printer is disconnected.

Plain `--fix` runs without sudo (`lpadmin`, `cupsdisable` and `cupsenable`
authenticate locally for members of `_lpadmin`) and only escalates to `--hard` on its
own if the printer is still stuck afterwards.

The underlying cause is likely electrical: the printer sits behind a USB hub chain,
and the current spike when the thermal head fires resets the device mid-job.
Plugging it straight into the Mac, or into a powered hub, reduces how often it
happens.

## Web service (print from the phone)

`server.py` runs the same detection without needing the Mac: open the page on
your phone, pick the PDF the carrier gave you, and it returns the crops at
label size, ready to open in a Bluetooth label app.

This exists because the cropping is the part that matters and it used to live
only on the Mac — Bluetooth solves printing from the phone, not cropping.

Dependencies are pinned. Without pins the server installed PyMuPDF 2.0 while
development ran 1.27, and 2.0 pulls `pymupdf_layout`, `pymupdf4llm` and
`onnxruntime` — around 114 MB of OCR and ML this app never calls, telemetry
included. Pinning cut the image from 639 MB to 415 MB and silenced the
startup errors.

```bash
git clone https://github.com/brunomartins84/thermal-label-cropper.git /srv/pdf-label
cd /srv/pdf-label && docker compose up -d --build
sudo cp deploy/nginx.conf /etc/nginx/sites-available/pdf-label
sudo ln -s /etc/nginx/sites-available/pdf-label /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

The container binds to `127.0.0.1:8000` only, so nginx on the host is the one
thing facing the internet. It runs as an unprivileged user with a read-only
filesystem, all capabilities dropped and `no-new-privileges`; the only writable
path is a 256 MB tmpfs at `/tmp` holding the crops, which disappears with the
container. Memory and PID limits are there because rendering a PDF is the
expensive step and the input comes from outside.

`deploy/pdf-label.service` is the systemd alternative if you would rather run it
straight on the host without Docker.

`deploy/nginx.conf` is the live site at `etiqueta.undershows.com.br`, HTTP only —
`certbot --nginx` adds the TLS block and the redirect itself, and pointing
`ssl_certificate` at a file that does not exist yet would make `nginx -t` fail
before certbot ever runs. It is behind basic auth: create the password file first, or `nginx -t` fails on
purpose rather than serving an open PDF renderer.

```bash
sudo htpasswd -c /etc/nginx/.htpasswd-pdf-label bruno
```

`client_max_body_size` must stay at or above `MAX_UPLOAD` in `server.py`, or
uploads die with a 413 before reaching the app.

Crops are written to a random directory under `/tmp` and swept after two hours;
there is no database and nothing is kept. Uploads are capped at 25 MB and 20
pages, and the download route rejects anything that is not a 16-hex token plus
a bare filename.

When detection is not confident — a single block covering most of the page —
the service has no manual fallback like the CLI does, so it returns the whole
page and says so.

## Project structure

```
crop_web.py   # CLI entry point and page processing logic
detector.py   # pixel-based block detection (no Flask dependency)
app.py        # browser fallback UI (Flask)
server.py     # web service: upload a PDF, get the crops back
deploy/       # systemd unit and nginx site for server.py
fit_label.py  # scales/rotates a crop onto the label before printing
magic         # zsh wrapper: crop, print, printer recovery
```
