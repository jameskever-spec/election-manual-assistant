#!/usr/bin/env python3
"""Render the manual's form/screenshot pages to images for the app.

Run this ONCE, from inside the election-app folder, pointing at your local
searchable manual PDF:

    python3 render_form_pages.py "/path/to/election_manual_deskewed_searchable.pdf"

Requires PyMuPDF:  python3 -m pip install pymupdf
"""
import sys
from pathlib import Path

PAGES = [2, 5, 6, 7, 9, 10, 15, 18, 19, 24, 25, 29, 30, 31, 32, 33, 34, 35, 39, 40, 42, 44, 58, 59, 60, 61, 62, 63, 64, 65, 69, 70, 76, 77, 80, 82, 84, 85, 91, 93, 94, 97, 98, 100, 101, 102, 103, 105, 110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 126, 127, 128, 130, 131, 132, 133, 135, 137, 138, 139, 140, 141, 142, 143, 145, 146, 147, 148, 149, 150, 153, 154, 155, 156, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 184, 185, 186, 188, 189, 191, 194, 197, 198, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 215, 216, 217, 218, 219, 222, 223, 226, 230, 231, 232, 234, 236, 237, 238, 239, 240, 241, 242, 248, 249, 256, 257, 258, 259, 261, 263, 265, 267, 268, 269, 273, 274, 278, 279, 280, 282, 283, 284, 285, 286, 289, 290, 301, 304]

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF is not installed. Run:  python3 -m pip install pymupdf")
        sys.exit(1)
    doc = fitz.open(sys.argv[1])
    out = Path(__file__).resolve().parent / "img"
    out.mkdir(exist_ok=True)
    done = 0
    for pg in PAGES:
        if pg - 1 >= len(doc):
            print(f"  page {pg} not in PDF, skipping")
            continue
        pix = doc[pg - 1].get_pixmap(dpi=140)
        fp = out / f"p{pg}.jpg"
        try:
            pix.save(str(fp), jpg_quality=78)
        except Exception:
            fp = out / f"p{pg}.png"
            pix.save(str(fp))
        done += 1
        print(f"  rendered p.{pg} -> img/{fp.name}")
    print(f"Done: {done} pages rendered into {out}")

if __name__ == "__main__":
    main()
