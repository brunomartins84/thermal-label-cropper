import numpy as np
import fitz


def mm_to_px(mm, zoom):
    return mm * 72 / 25.4 * zoom


def rect_mm(rect):
    return rect.width * 25.4 / 72, rect.height * 25.4 / 72


def _remove_thin_bridges(arr, max_bridge_px):
    arr = arr.copy()
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


def _scan_axis(mask, axis, zoom, min_gap_mm, max_bridge_mm, margin_mm, pix_w, pix_h):
    """
    Scan along one axis (0=rows/vertical, 1=cols/horizontal).
    Returns list of (start, end) band pairs in pixel coords of that axis.
    """
    has_content = mask.any(axis=axis)
    has_content = _remove_thin_bridges(has_content, mm_to_px(max_bridge_mm, zoom))
    min_gap_px = mm_to_px(min_gap_mm, zoom)
    margin_px = mm_to_px(margin_mm, zoom)
    dim = pix_h if axis == 1 else pix_w

    bands = []
    in_band = False
    gap = 0
    start = 0
    for i, has in enumerate(has_content):
        if has:
            if not in_band:
                start = i
                in_band = True
            gap = 0
        elif in_band:
            gap += 1
            if gap > min_gap_px:
                bands.append((max(0, start - margin_px), min(dim - 1, i - gap + margin_px)))
                in_band = False
    if in_band:
        bands.append((max(0, start - margin_px), min(dim - 1, len(has_content) - 1 + margin_px)))

    return bands


def detect_regions(page, zoom=3, threshold=245, min_gap_mm=5,
                   max_bridge_mm=1.5, margin_mm=2):
    """
    Detecta blocos de conteúdo na página escaneando tanto vertical quanto
    horizontalmente. Retorna lista de fitz.Rect ordenada de cima pra baixo,
    esquerda pra direita.
    """
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = img[..., :3].mean(axis=2)
    mask = gray < threshold

    kwargs = dict(zoom=zoom, min_gap_mm=min_gap_mm, max_bridge_mm=max_bridge_mm,
                  margin_mm=margin_mm, pix_w=pix.width, pix_h=pix.height)

    row_bands = _scan_axis(mask, axis=1, **kwargs)  # horizontal gaps → vertical bands
    regions = []

    for y0, y1 in row_bands:
        y0, y1 = int(y0), int(y1)
        row_slice = mask[y0:y1 + 1, :]
        col_bands = _scan_axis(row_slice, axis=0, **kwargs)  # vertical gaps → horizontal bands

        if len(col_bands) > 1:
            # Multiple columns inside this row band
            for x0, x1 in col_bands:
                x0, x1 = int(x0), int(x1)
                regions.append(fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom))
        else:
            # Single column — use full horizontal extent of content
            cols = np.where(row_slice.any(axis=0))[0]
            if len(cols) == 0:
                continue
            margin_px = mm_to_px(margin_mm, zoom)
            x0 = max(0, int(cols.min()) - margin_px)
            x1 = min(pix.width - 1, int(cols.max()) + margin_px)
            regions.append(fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom))

    return regions


def get_page_image(page, zoom=2):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png"), zoom
