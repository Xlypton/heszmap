"""Turn a district's plan annexes (PDF, or images) into sheet images plus a text layer.

- Scanned page (one big embedded image): the image is extracted as is, no re-encoding.
- Vector page: rendered at the configured DPI, and its text (zone codes, parcel numbers, street
  names) is taken from the PDF itself and written in the same format plan_ocr.py produces, so the
  later steps work the same way and no OCR is needed.

Usage: python3 scripts/plan_sheets.py xx
Writes scripts/.cache/<key>/sheet<i>.(jpg|png) and, for vector pages, scripts/plans/<key>-ocr-<i>.json.
"""
import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district  # noqa: E402
import njt  # noqa: E402
from plan_probe import probe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FONT_FIX = None  # plan.font_fix of the district being processed (see text_layer)


def text_layer(page: pymupdf.Page, zoom: float) -> list[dict]:
    """Words and lines with their rotated boxes, in sheet pixels (plan_ocr.py's format)."""
    out = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(ch["c"] for span in line["spans"] for ch in span["chars"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            dx, dy = line["dir"]  # unit vector of the writing direction
            # Rotated quad: along the baseline direction, with the line's height across it.
            chars = [ch for span in line["spans"] for ch in span["chars"]]
            first, last = chars[0]["bbox"], chars[-1]["bbox"]
            h = max(span["size"] for span in line["spans"])
            ox, oy = (first[0] + first[2]) / 2, (first[1] + first[3]) / 2
            ex, ey = (last[0] + last[2]) / 2, (last[1] + last[3]) / 2
            nx, ny = -dy * h / 2, dx * h / 2
            quad = [(ox - nx, oy - ny), (ex - nx, ey - ny), (ex + nx, ey + ny), (ox + nx, oy + ny)] \
                if abs(ex - ox) + abs(ey - oy) > 1 else [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            if page.rotation:  # text coordinates are unrotated; the rendered sheet is rotated (Budapest I.: 270°)
                quad = [tuple(pymupdf.Point(x, y) * page.rotation_matrix) for x, y in quad]
            out.append({"text": text, "conf": 1.0, "box": [[round(x * zoom), round(y * zoom)] for x, y in quad]})
    # Text in a subset font without a Unicode map comes out shifted ("XWFD" for "utca"; Budapest I.):
    # plan.font_fix = {"shift": 29, "map": {"~": "ú", ...}} decodes it. A line is replaced only when
    # every character decodes to a letter, digit, space or common punctuation.
    fix = FONT_FIX
    if fix:
        for l in out:
            t = l["text"]
            if "\x03" not in t and not any(t.endswith(s) for s in fix.get("suffixes", [])):
                continue
            dec = "".join(fix["map"].get(c) or (chr(ord(c) + fix["shift"]) if 0x21 <= ord(c) <= 0x5f else "\0") for c in t)
            if "\0" not in dec and all(ch.isalnum() or ch in " .-/()" for ch in dec):
                l["text"] = dec
    # Some CAD exports draw bold text by printing it many times with tiny offsets (Budapest VI.: each
    # zone code ~30 times): keep one copy of the same text within 5 px.
    seen, kept = {}, []
    for l in out:
        cx, cy = sum(p[0] for p in l["box"]) / 4, sum(p[1] for p in l["box"]) / 4
        near = seen.setdefault(l["text"], [])
        if any(abs(cx - x) <= 5 and abs(cy - y) <= 5 for x, y in near):
            continue
        near.append((cx, cy))
        kept.append(l)
    return kept


def main():
    global FONT_FIX
    key = sys.argv[1]
    cfg = district.load(key)
    FONT_FIX = cfg["plan"].get("font_fix")
    work = district.work_dir(key)
    for old in list(work.glob("sheet*.png")) + list(work.glob("sheet*.jpg")):
        old.unlink()
    i = 0
    for ref in cfg["plan"]["annexes"]:
        url = ref if ref.startswith("http") else njt.NJT + ref
        pdf = njt.download(url, work / "annex" / Path(url).name)
        if pdf.suffix.lower() in (".png", ".jpg", ".jpeg"):
            # Some plans are published as images (Csobánka): the image is the sheet, as is.
            dest = work / f"sheet{i}{'.jpg' if pdf.suffix.lower() == '.jpeg' else pdf.suffix.lower()}"
            dest.write_bytes(pdf.read_bytes())
            print(f"sheet{i}: image annex {pdf.name}")
            i += 1
            continue
        if cfg["plan"].get("rasterize_dpi"):
            # A raster plan cut into many image strips (Budapest II.: 600 dpi strips, no text layer):
            # render each page as one image at this dpi; it is then OCR'd and fitted like an image plan.
            dpi = cfg["plan"]["rasterize_dpi"]
            for page in pymupdf.open(pdf):
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                dest = work / f"sheet{i}.png"
                pix.save(dest)
                print(f"sheet{i}: page {page.number + 1} of {pdf.name} rendered at {dpi} dpi, {pix.width}x{pix.height} px")
                i += 1
            continue
        info = probe(str(pdf))
        doc = pymupdf.open(pdf)
        # plan_probe profiles the first pages only: later pages are taken to be like the last one profiled.
        for page in doc:
            pinfo = {**info["pages"][min(page.number, len(info["pages"]) - 1)], "page": page.number + 1}
            if cfg["plan"].get("pages") and page.number + 1 not in cfg["plan"]["pages"]:
                continue  # e.g. a legend page in front of the map sheets (Budapest I.)
            if pinfo["kind"] == "scan":
                xref = max(page.get_images(full=True), key=lambda im: im[2] * im[3])[0]
                img = doc.extract_image(xref)
                dest = work / f"sheet{i}.{'jpg' if img['ext'] in ('jpg', 'jpeg') else 'png'}"
                dest.write_bytes(img["image"])
                print(f"sheet{i}: scanned page {pinfo['page']} of {pdf.name}, {img['width']}x{img['height']} px")
            else:
                zoom = cfg["plan"]["dpi"] / 72
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                dest = work / f"sheet{i}.png"
                pix.save(dest)
                labels = text_layer(page, zoom)
                (ROOT / "scripts/plans" / f"{key}-ocr-{i}.json").write_text(json.dumps(
                    {"image": dest.name, "size": [pix.width, pix.height], "labels": labels, "source": "pdf-text"},
                    ensure_ascii=False))
                print(f"sheet{i}: vector page {pinfo['page']} of {pdf.name}, {pix.width}x{pix.height} px, {len(labels)} text lines")
            i += 1


if __name__ == "__main__":
    main()
