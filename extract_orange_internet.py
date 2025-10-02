# save as: extract_orange_internet.py
# run:
#   uv run extract_orange_internet.py "/path/to/folder/with/pdfs"
# or:
#   python extract_orange_internet.py "/path/to/folder/with/pdfs"

import sys, re, glob, os, datetime as dt
import csv
import unicodedata
import fitz  # PyMuPDF

# --- Patterns ---
# Strict "usage" amount: e.g. "99 Go" or "88,2 Mo" NOT followed by "en ..."
USAGE_AMOUNT_RE = re.compile(r'(\d+[.,]?\d*)\s*(Go|Mo)(?!\s*en\b)', re.IGNORECASE)

# Generic amount (only used in late fallbacks)
AMOUNT_RE = re.compile(r'(\d+[.,]?\d*)\s*(Go|Mo)', re.IGNORECASE)

DATE_FACTURE_RE = re.compile(r'date de facture\s*:\s*(\d{2}/\d{2}/\d{2})', re.IGNORECASE)
# Some Orange PDFs show only "votre facture mobile du 06.08.2025"
ALT_DATE_RE = re.compile(r'votre facture mobile du\s*(\d{2}\.\d{2}\.\d{4})', re.IGNORECASE)

PERIOD_RE = re.compile(r'période du\s*(\d{2}\.\d{2}\.\d{4})\s*au\s*(\d{2}\.\d{2}\.\d{4})', re.IGNORECASE)

# Obvious allowance / plan text to ignore
OFFER_NOISE = (
    "votre offre",
    "appels/sms/mms",
    "go en fr métrop", "go en fr metrop",
    "eu/dom/suisse/andorre", "eu/dom", "suisse/andorre",
    "détails et conditions", "details et conditions",
    "forfait 170 go", "170 go", "100 go",
    "go en eu", "depuis les zones",
)

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != 'Mn')

def to_float_gb(value_str: str, unit: str) -> float:
    x = float(value_str.replace(',', '.'))
    return x if unit.lower() == 'go' else x / 1024.0

def usage_amounts(snippet: str):
    return [to_float_gb(v, u) for (v, u) in USAGE_AMOUNT_RE.findall(snippet)]

def any_amounts(snippet: str):
    return [to_float_gb(v, u) for (v, u) in AMOUNT_RE.findall(snippet)]

def looks_like_offer_block(text_block: str) -> bool:
    low = text_block.lower()
    low_na = strip_accents(low)
    return any(p in low or p in low_na for p in OFFER_NOISE)

def parse_invoice(raw_text: str):
    # Normalise unicode and spaces
    norm = unicodedata.normalize("NFKC", raw_text).replace("\u00a0", " ")
    # Keep both original-case lines and lowercased, accent-stripped helpers
    lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
    lines_na = [strip_accents(ln.lower()) for ln in lines]

    # Invoice date
    inv_date = None
    m = DATE_FACTURE_RE.search(norm)
    if m:
        inv_date = dt.datetime.strptime(m.group(1), "%d/%m/%y").date()
    else:
        m2 = ALT_DATE_RE.search(norm)
        if m2:
            inv_date = dt.datetime.strptime(m2.group(1), "%d.%m.%Y").date()

    # Billing period (take the last)
    period_start = period_end = None
    periods = PERIOD_RE.findall(norm)
    if periods:
        start_s, end_s = periods[-1]
        period_start = dt.datetime.strptime(start_s, "%d.%m.%Y").date()
        period_end = dt.datetime.strptime(end_s, "%d.%m.%Y").date()

    # 1) Anchor on domestic usage row: connexion + internet + france (metropol*)
    candidates = []
    for i, (ln, ln_na) in enumerate(zip(lines, lines_na)):
        if ("connexion" in ln_na and "internet" in ln_na
            and "france" in ln_na
            and ("metropolitaine" in ln_na or "metropol" in ln_na or "france" in ln_na)):
            window = " | ".join(lines[i:i+8])  # current + next 7 lines
            if not looks_like_offer_block(window):
                candidates.extend(usage_amounts(window))

    # 2) Fallback A: any line mentioning 'internet' but skipping obvious plan blocks, still using strict usage amounts
    if not candidates:
        for i, (ln, ln_na) in enumerate(zip(lines, lines_na)):
            if "internet" in ln_na:
                window = " | ".join(lines[i:i+6])
                if not looks_like_offer_block(window):
                    candidates.extend(usage_amounts(window))

    # 3) Fallback B: last resort, scan whole doc for strict usage amounts,
    #    then throw away outliers >= 120 Go which are likely plan numbers.
    if not candidates:
        all_vals = usage_amounts(norm)
        candidates = [v for v in all_vals if v < 120.0] or all_vals

    internet_gb = max(candidates) if candidates else None
    return inv_date, period_start, period_end, internet_gb

def extract_from_pdf(path: str):
    with fitz.open(path) as doc:
        texts = []
        for page in doc:
            texts.append(page.get_text("text"))
        full_text = "\n".join(texts)
    return parse_invoice(full_text)

def main(folder: str):
    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    if not pdfs:
        print(f"No PDFs found in: {folder}")
        sys.exit(1)

    rows = []
    for pdf in pdfs:
        inv_date, p_start, p_end, gb = extract_from_pdf(pdf)
        rows.append({
            "file": os.path.basename(pdf),
            "invoice_date": inv_date.isoformat() if inv_date else "",
            "period_start": p_start.isoformat() if p_start else "",
            "period_end": p_end.isoformat() if p_end else "",
            "internet_gb": round(gb, 3) if gb is not None else ""
        })

    out_csv = os.path.join(os.path.dirname(__file__), "orange_internet_usage.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file","invoice_date","period_start","period_end","internet_gb"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {out_csv}")
    for r in rows:
        print(r)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python extract_orange_internet.py "/path/with/pdfs"')
        sys.exit(1)
    main(sys.argv[1])
