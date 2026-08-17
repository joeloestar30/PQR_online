import argparse
import csv
import io
import re
import ssl
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.phivolcs import fetch_latest_events


try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


STOP_PHRASES = (
    "The figure above",
    "This is an aftershock",
    "This event is reportedly",
    "Expecting Damage",
    "Expecting Aftershocks",
    "Issued On",
    "Prepared by",
    "IMPORTANT",
)


class BulletinCellParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.in_cell = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in {"td", "th"}:
            self.in_cell = True
            self.buffer = []
        elif self.in_cell and tag == "br":
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.in_cell:
            text = normalize_space("".join(self.buffer))
            self.cells.append(text)
            self.buffer = []
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.buffer.append(data)


def normalize_space(value):
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def fetch_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PQR-Web-App"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except ssl.SSLError:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read()
    except urllib.error.URLError as error:
        if "CERTIFICATE_VERIFY_FAILED" not in str(error):
            raise
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read()


def pdf_text(data):
    if PdfReader is None:
        raise RuntimeError("PDF extraction requires pypdf. Use the bundled workspace Python or install pypdf.")
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def html_cells(data):
    parser = BulletinCellParser()
    parser.feed(data.decode("utf-8", "replace"))
    return [cell for cell in parser.cells if cell]


def clean_intensity_text(value):
    text = normalize_space(value)
    text = re.sub(r"^\d+\.\d+[a-z]?\s+\d{4}_\d{4}_\d{4}_[A-Za-z0-9_]+\s*", "", text)
    text = re.sub(r"^Reported Intensities\s*:?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^Instrumental Intensities\s*:?\s*", "", text, flags=re.IGNORECASE)
    for phrase in STOP_PHRASES:
        index = text.find(phrase)
        if index >= 0:
            text = text[:index].strip()
    return text


def split_intensity_blob(blob):
    text = clean_intensity_text(blob)
    if not text:
        return "", ""

    marker = re.search(r"\bInstrumental Intensities\s*:", text, flags=re.IGNORECASE)
    if marker:
        reported = clean_intensity_text(text[: marker.start()])
        instrumental = clean_intensity_text(text[marker.end() :])
        return reported, instrumental

    if re.search(r"\bReported Intensities\s*:", text, flags=re.IGNORECASE):
        reported = re.split(r"\bReported Intensities\s*:", text, flags=re.IGNORECASE, maxsplit=1)[1]
        return clean_intensity_text(reported), ""

    if re.search(r"\bIntensity\s+[IVX]+", text):
        return text, ""

    return "", ""


def extract_from_html(data):
    cells = html_cells(data)
    candidates = []
    for cell in cells:
        if "Intensit" in cell or re.search(r"\bIntensity\s+[IVX]+", cell):
            candidates.append(cell)
    for cell in candidates:
        reported, instrumental = split_intensity_blob(cell)
        if reported or instrumental:
            return reported, instrumental, ""
    return "", "", "No intensity text found"


def extract_from_pdf(data):
    text = normalize_space(pdf_text(data))
    lower = text.lower()
    start_positions = [
        pos
        for pos in (
            lower.find("reported intensities"),
            lower.find("instrumental intensities"),
            lower.find("intensity "),
        )
        if pos >= 0
    ]
    if not start_positions:
        return "", "", "No intensity text found"
    blob = text[min(start_positions) :]
    return (*split_intensity_blob(blob), "")


def extract_bulletin_intensities(url):
    data = fetch_bytes(url)
    if url.lower().endswith(".pdf"):
        return extract_from_pdf(data)
    return extract_from_html(data)


def main():
    parser = argparse.ArgumentParser(description="Extract intensities from PHIVOLCS earthquake bulletins.")
    parser.add_argument("--limit", type=int, default=100, help="Number of latest bulletins to process. Use 0 for all parsed table rows.")
    parser.add_argument("--output", default="output/phivolcs_intensities.csv", help="CSV output path.")
    args = parser.parse_args()

    limit = None if args.limit == 0 else args.limit
    events = fetch_latest_events(limit=limit or 10000)
    output_path = ROOT_DIR / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for event in events:
        try:
            reported, instrumental, note = extract_bulletin_intensities(event.source_url)
        except Exception as error:
            reported, instrumental, note = "", "", f"{type(error).__name__}: {error}"
        rows.append(
            {
                "event_key": event.event_key,
                "ph_time": event.ph_time,
                "magnitude": event.magnitude,
                "reference_location": event.reference_location,
                "source_url": event.source_url,
                "reported_intensities": reported,
                "instrumental_intensities": instrumental,
                "note": note,
            }
        )

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys() if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    with_intensity = sum(1 for row in rows if row["reported_intensities"] or row["instrumental_intensities"])
    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"Rows with intensity text: {with_intensity}")


if __name__ == "__main__":
    main()
