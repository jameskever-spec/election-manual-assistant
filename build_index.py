#!/usr/bin/env python3
"""Build precomputed search data for the Election Manual Assistant PWA.

Reads manual_pages.json (pages + chunks) and emits js/data.js containing:
  - CHUNKS: [{id, page, label, text}]
  - PAGES: {page: {label, text}}
  - INDEX: inverted index {term: [[chunkIdx, tf], ...]}
  - DOCLEN: [len per chunk], AVGDL, N

Stemming here MUST match the stem() function in js/app.js exactly.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = Path("/mnt/user-data/uploads/manual_pages.json")
OUT = ROOT / "js" / "data.js"

TOKEN_RE = re.compile(r"[a-z0-9]+")

JUNK_SYMBOLS = set("|_—=~^<>{}[]@#$%*\\/")
PAGE_REF_RE = re.compile(r"^\s*(?:\d{1,2}-\d{1,3})\s*$")


def _bad_token(t: str) -> bool:
    core = re.sub(r"[^A-Za-z]", "", t)
    if not core:
        return len(t) > 1  # punctuation clumps like "_|" "—|"
    if len(core) >= 4 and not re.search(r"[aeiouAEIOU]", core):
        return True  # vowelless OCR soup: "SrStm", "xprns"
    if re.search(r"[a-z][A-Z]", t):
        return True  # mid-word capitals: "SrStEM", "PowerLight" — OCR artifacts
    return False


def is_junk_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if not re.search(r"[A-Za-z0-9]", s):
        return True  # pure symbol lines: "|", "—|"
    weird = sum(1 for ch in s if ch in JUNK_SYMBOLS)
    if weird >= 2 and weird / len(s) > 0.10:
        return True  # pipe-framed OCR fragments: "| Satvery ight |"
    toks = s.split()
    if not toks:
        return False
    # Split-word OCR artifacts on short lines: "Launch E xprens Pot"
    if len(toks) <= 4 and any(re.fullmatch(r"[B-HJ-Z]", t) for t in toks):
        return True
    bad = sum(1 for t in toks if _bad_token(t))
    return bad / len(toks) >= 0.45


# Explicit, unambiguous OCR corrections — mechanical only, never rewording.
OCR_FIXES = [
    (re.compile(r"(?m)^lf\b"), "If"),
    (re.compile(r"\bIfa\b"), "If a"),
    (re.compile(r"\bAvoter\b"), "A voter"),
    (re.compile(r"\bAperson\b"), "A person"),
    (re.compile(r"\bAregistered\b"), "A registered"),
    (re.compile(r"\bAcandidate\b"), "A candidate"),
    (re.compile(r"\bAprovisional\b"), "A provisional"),
    (re.compile(r"\bAcopy\b"), "A copy"),
    (re.compile(r"\bAtleast\b"), "At least"),
    (re.compile(r"\bAssoon\b"), "As soon"),
    (re.compile(r"\bAllselections\b"), "All selections"),
]


# Corpus token frequencies — set in main() before cleaning. A 305-page manual
# is its own dictionary: real words repeat, OCR junk is near-unique.
CORPUS_FREQ: dict[str, int] = {}

GLYPH_PREFIX = re.compile(r"^[A-Za-z]?[\\/|]+\s+")  # warning-triangle etc. misreads


def _rare(t: str) -> bool:
    runs = re.findall(r"[A-Za-z]+", t)
    if not runs:
        return False
    core = max(runs, key=len).lower()  # "Driver's" -> "driver", not "drivers"
    return len(core) >= 4 and CORPUS_FREQ.get(core, 0) < 3


def is_fragment_line(s: str) -> bool:
    """Short lines composed mostly of near-unique tokens are OCR debris from
    form images and figures ('Vater Signature', 'neeae\"')."""
    toks = s.split()
    if not toks or len(toks) > 6:
        return False
    rare = sum(1 for t in toks if _rare(t))
    ratio = rare / len(toks)
    if ratio == 0:
        return False
    # Lowercase lines ending in sentence punctuation are prose continuations
    # ("video conference.") — form-image debris is never shaped like that.
    if re.fullmatch(r"[a-z][a-z .,;:'\-]*[.,;:]", s):
        return False
    if ratio > 0.5:
        return True
    # At exactly half rare: sentence tails are legit continuations —
    # form-image debris almost never ends a sentence ('!' doesn't count:
    # 'O18 Goenatarie!' is not a sentence).
    return ratio == 0.5 and not re.search(r"[.,;:]$", s)


def is_short_soup(s: str) -> bool:
    """Screen-text OCR junk ('AA, ve rset dose pot ort og dc.', 'ee ots') is a
    soup of short tokens with no common-word skeleton. Real English lines keep
    a skeleton of frequent words; lines with digits carry meaning in numbers."""
    if re.search(r"\d", s):
        return False
    toks = re.findall(r"[A-Za-z]+", s)
    if len(toks) < 2:
        return False
    mean = sum(len(t) for t in toks) / len(toks)
    if mean > 3.2:
        return False
    common = sum(1 for t in toks if CORPUS_FREQ.get(t.lower(), 0) >= 100)
    return common / len(toks) < 0.34


def clean_page_text(text: str) -> str:
    """Junk filtering + bullet normalization + orphan-marker merging."""
    for pat, rep in OCR_FIXES:
        text = pat.sub(rep, text)
    raw = text.splitlines()
    out: list[str] = []
    pending_bullet = False
    fig_shadow = 0  # label-lines remaining in a figure's "shadow"
    for ln in raw:
        s = GLYPH_PREFIX.sub("", ln.strip())
        if is_junk_line(s):
            continue
        # Figure captions cast a shadow: the short label-lines that follow are
        # the figure's innards (sample-ballot text, device labels), not prose.
        if re.match(r"(?i)^figure\s*[-—:]", s):
            fig_shadow = 16
            out.append(s)
            continue
        if len(s) == 1 and s != "•":
            # Lone character: either an orphan bullet marker or OCR debris
            if s.lower() in {"o", "*", "¢", "e"}:
                pending_bullet = True
            continue
        # Tiny fragments ('it', 'Hh', 'al') — keep page refs and bare numbers
        if len(s) <= 3 and not PAGE_REF_RE.match(s) and not s.isdigit():
            continue
        if CORPUS_FREQ and (is_fragment_line(s) or is_short_soup(s)):
            continue
        if s == "•":
            pending_bullet = True
            continue
        if fig_shadow > 0:
            words = s.split()
            is_label = (
                len(words) <= 4
                and not re.search(r"[.,;:]$", s)
                and not re.match(r"^[o0O•*¢e]\s", s)
                and not re.match(r"^\d+[.)]", s)
                and not PAGE_REF_RE.match(s)
            )
            if is_label:
                fig_shadow -= 1
                continue
            fig_shadow = 0  # real prose resumes; shadow ends
        # Normalize bullet prefixes to a consistent glyph ('e' is a common
        # Tesseract misread of the bullet glyph — verified corpus-wide)
        m = re.match(r"^[o0O•*¢e]\s+(?=\S)", s)
        if m:
            s = "• " + s[m.end():]
        elif pending_bullet:
            s = "• " + s
        pending_bullet = False
        out.append(s)
    return "\n".join(out)


def repair_label(label: str, cleaned_text: str, page: int) -> str:
    """Back-matter pages sometimes carry garbage labels like 'e' or 'Ww'."""
    if label and len(label.strip()) >= 4 and re.search(r"[A-Za-z]{3}", label):
        return label.strip()
    for ln in cleaned_text.splitlines():
        s = ln.strip().lstrip("• ")
        if len(s) >= 12 and len(s.split()) >= 3:
            return s[:60].rstrip(" ,;:-")
    return f"Manual p. {page}"


def strict_clean(text: str) -> str:
    """Extra pass for tier-1 (screenshot/form) pages, where the page image is
    the real content and text is search fodder. Repeated screenshot junk
    ('Secuty', 'Repart') poisons corpus frequency, so lines here must be built
    from genuinely common words to survive."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r"(?i)^figure\s*[-—:]", s) or PAGE_REF_RE.match(s):
            out.append(s)
            continue
        toks = re.findall(r"[A-Za-z]+", s)
        if not toks:
            continue
        common = sum(1 for t in toks if CORPUS_FREQ.get(t.lower(), 0) >= 20)
        ratio = common / len(toks)
        if len(toks) >= 4 and ratio >= 0.75:
            out.append(s)
        elif len(toks) < 4 and ratio == 1.0:
            out.append(s)
    return "\n".join(out)


SENT_END = re.compile(r"[.!?:;][\"\u201D\u2019)]?$")


def chunk_page(cleaned_text: str, target: int = 700, hard: int = 1100):
    """Sentence-aware chunking: prefer to break after a line that ends a
    sentence (or before a heading-like line), never leaving tiny fragments."""
    lines = [ln for ln in cleaned_text.splitlines() if ln.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for i, ln in enumerate(lines):
        cur.append(ln)
        size += len(ln) + 1
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        heading_next = nxt is not None and len(nxt.split()) <= 6 and not nxt.startswith("•")
        if size >= hard or (size >= target and (SENT_END.search(ln.strip()) or heading_next)):
            chunks.append("\n".join(cur))
            cur, size = [], 0
    if cur:
        tail = "\n".join(cur)
        if chunks and len(tail) < 200:
            chunks[-1] = chunks[-1] + "\n" + tail
        else:
            chunks.append(tail)
    return chunks


def is_glossary_page(text: str) -> bool:
    """Glossary pages are runs of 'Term: definition' lines — keyword magnets
    that define everything and instruct nothing."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    defs = sum(1 for ln in lines if re.match(r"^[\"\u201C(]?[A-Z][A-Za-z ()/\u2019'\u201D\"-]{2,60}:\s+\S", ln))
    if defs >= 6:
        return True
    return defs >= 3 and lines and defs / len(lines) >= 0.3


def is_toc_page(text: str) -> bool:
    """Chapter-opener contents pages: runs of bare page refs, or a 'Chapter N'
    heading followed mostly by short topic-title lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    refs = sum(1 for ln in lines if PAGE_REF_RE.match(ln))
    if refs >= 3:
        return True
    if re.match(r"(?i)^chapter\s+\d+", lines[0]) and len(lines) >= 6:
        short = sum(1 for ln in lines if len(ln.split()) <= 6)
        if short / len(lines) >= 0.6:
            return True
    return lines[0].lower().startswith("table of contents")


def stem(w: str) -> str:
    # Mirror of JS stem() — keep in sync.
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ses", "xes", "zes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    return w


def tokenize(text: str):
    return [stem(t) for t in TOKEN_RE.findall(text.lower())]


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    chunks = data["chunks"]
    pages = data["pages"]

    # Pass 1: corpus token frequencies (the manual validates its own words)
    for p in pages:
        for t in re.findall(r"[A-Za-z]+", p["text"]):
            t = t.lower()
            CORPUS_FREQ[t] = CORPUS_FREQ.get(t, 0) + 1

    # OCR quality tiers: tier 1 = form/screenshot pages (text unreliable,
    # candidates for page images); tier 2 = mild figure junk.
    def deg_tier(p) -> int:
        toks = re.findall(r"[A-Za-z]+", p["text"])
        n = max(len(toks), 1)
        sus = (
            sum(1 for t in toks if len(t) >= 4 and CORPUS_FREQ.get(t.lower(), 0) < 3) / n
            if len(toks) >= 20 else 0.0
        )
        checkbox = len(re.findall(r"©", p["text"]))
        figures = len(re.findall(r"Figure\s*[-—]", p["text"]))
        if sus >= 0.15 or checkbox >= 3:
            return 1
        if sus > 0.06 or figures >= 2:
            return 2
        return 0

    tiers = {p["pdf_page"]: deg_tier(p) for p in pages}

    # The cleaner itself measures degradation: pages losing most of their
    # lines to the junk filters are screenshot/form pages even if token
    # stats missed them. (Median page loses ~20% — thresholds sit well above.)
    for p in pages:
        raw_n = sum(1 for ln in p["text"].splitlines() if ln.strip())
        if raw_n < 8:
            continue
        kept_n = sum(1 for ln in clean_page_text(p["text"]).splitlines() if ln.strip())
        removed = 1 - kept_n / raw_n
        if removed >= 0.50:
            tiers[p["pdf_page"]] = 1
        elif removed >= 0.28:
            tiers[p["pdf_page"]] = max(tiers[p["pdf_page"]], 2)

    tier1_pages = sorted(pg for pg, t in tiers.items() if t == 1)
    render_pages = sorted(pg for pg, t in tiers.items() if t in (1, 2))

    # Build chunk & page stores from OUR pipeline (ignore inherited chunks):
    # clean text, repair labels, flag TOCs, re-chunk sentence-aware.
    toc_pages = {p["pdf_page"] for p in pages if is_toc_page(p["text"])}
    glossary_pages = {p["pdf_page"] for p in pages if is_glossary_page(p["text"])}
    chunk_store = []
    page_store = {}
    for p in pages:
        cleaned = clean_page_text(p["text"])
        if tiers.get(p["pdf_page"]) in (1, 2):
            cleaned = strict_clean(cleaned)
        label = repair_label(p.get("label") or "", cleaned, p["pdf_page"])
        if p["pdf_page"] in glossary_pages:
            label = "Glossary"
        entry = {"label": label, "text": cleaned}
        if p["pdf_page"] in toc_pages:
            entry["toc"] = 1
        if p["pdf_page"] in glossary_pages:
            entry["glo"] = 1
        if tiers.get(p["pdf_page"]):
            entry["deg"] = tiers[p["pdf_page"]]
        page_store[str(p["pdf_page"])] = entry
        for j, ctext in enumerate(chunk_page(cleaned)):
            ch = {
                "id": f"p{p['pdf_page']:03d}_c{j:02d}",
                "page": p["pdf_page"], "label": label, "text": ctext,
            }
            if p["pdf_page"] in toc_pages:
                ch["toc"] = 1
            if p["pdf_page"] in glossary_pages:
                ch["glo"] = 1
            chunk_store.append(ch)

    # Inverted index over chunk text + label (label terms get indexed too)
    index: dict[str, list] = {}
    doclen = []
    for i, c in enumerate(chunk_store):
        toks = tokenize(c["text"]) + tokenize(c["label"] or "") * 2  # label terms weighted x2
        doclen.append(len(toks))
        tf: dict[str, int] = {}
        for t in toks:
            if len(t) < 2:
                continue
            tf[t] = tf.get(t, 0) + 1
        for t, n in tf.items():
            index.setdefault(t, []).append([i, n])

    n = len(chunk_store)
    avgdl = sum(doclen) / n

    # Map manual page labels ("10-23") to PDF pages, for linkable TOC refs
    label_re = re.compile(r"\b(\d{1,2}-\d{1,3})\b")
    labelmap: dict[str, int] = {}
    for p in pages:
        for m in label_re.findall(p.get("label") or ""):
            labelmap.setdefault(m, p["pdf_page"])
    # Fallback: the printed page ref usually appears in the first/last lines
    edge_re = re.compile(r"^(\d{1,2}-\d{1,3})\b|\b(\d{1,2}-\d{1,3})$")
    for p in pages:
        lines = [ln.strip() for ln in p["text"].splitlines() if ln.strip()]
        for ln in lines[:3] + lines[-3:]:
            m = edge_re.search(ln)
            if m:
                labelmap.setdefault(m.group(1) or m.group(2), p["pdf_page"])

    payload = {
        "CHUNKS": chunk_store,
        "PAGES": page_store,
        "INDEX": index,
        "DOCLEN": doclen,
        "AVGDL": round(avgdl, 2),
        "N": n,
        "MIN_PAGE": min(p["pdf_page"] for p in pages),
        "MAX_PAGE": max(p["pdf_page"] for p in pages),
        "LABELMAP": labelmap,
    }
    js = "// Generated by build_index.py — do not edit by hand.\nconst MANUAL_DATA = " + json.dumps(
        payload, separators=(",", ":")
    ) + ";\n"
    OUT.write_text(js, encoding="utf-8")

    # Emit the local page-image render script with the tier-1 list baked in
    render_script = f'''#!/usr/bin/env python3
"""Render the manual's form/screenshot pages to images for the app.

Run this ONCE, from inside the election-app folder, pointing at your local
searchable manual PDF:

    python3 render_form_pages.py "/path/to/election_manual_deskewed_searchable.pdf"

Requires PyMuPDF:  python3 -m pip install pymupdf
"""
import sys
from pathlib import Path

PAGES = {render_pages}

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
            print(f"  page {{pg}} not in PDF, skipping")
            continue
        pix = doc[pg - 1].get_pixmap(dpi=140)
        fp = out / f"p{{pg}}.jpg"
        try:
            pix.save(str(fp), jpg_quality=78)
        except Exception:
            fp = out / f"p{{pg}}.png"
            pix.save(str(fp))
        done += 1
        print(f"  rendered p.{{pg}} -> img/{{fp.name}}")
    print(f"Done: {{done}} pages rendered into {{out}}")

if __name__ == "__main__":
    main()
'''
    (ROOT / "render_form_pages.py").write_text(render_script, encoding="utf-8")

    # Image manifest for the service worker's offline precache
    (ROOT / "js" / "imglist.js").write_text(
        "// Generated by build_index.py\nconst IMG_PAGES = " + json.dumps(render_pages) + ";\n",
        encoding="utf-8",
    )

    print(f"chunks={n} pages={len(page_store)} terms={len(index)} avgdl={avgdl:.1f}")
    print(f"tier1: {len(tier1_pages)} | render list (t1+t2): {len(render_pages)} pages")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
