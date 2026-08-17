import re
import ssl
import io
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

from modules.timeutils import parse_datetime_local_as_utc, phivolcs_datetime_to_utc_key
from modules.timeutils import parse_utc_iso, utc_now

PHIVOLCS_URL = "https://earthquake.phivolcs.dost.gov.ph/"
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
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


@dataclass
class PhivolcsEvent:
    ph_time: str
    event_key: str
    event_datetime_utc: str
    latitude: float | None
    longitude: float | None
    depth_km: float | None
    magnitude: float | None
    reference_location: str
    region_code: str
    source_url: str


class EarthquakeTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.in_cell = False
        self.current_cells = []
        self.current_text = []
        self.current_link = ""
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_row = True
            self.current_cells = []
            self.current_link = ""
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self.current_text = []
        elif self.in_cell and tag == "a" and attrs.get("href") and not self.current_link:
            self.current_link = attrs["href"]
        elif self.in_cell and tag == "br":
            self.current_text.append(" ")

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.in_cell:
            text = normalize_space("".join(self.current_text))
            self.current_cells.append(text)
            self.current_text = []
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_cells:
                self.rows.append((self.current_cells, self.current_link))
            self.in_row = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_text.append(data)


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


class BulletinTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buffer = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "xml"}:
            self.skip_depth += 1
        elif tag in {"br", "p", "tr", "td", "th", "div"}:
            self.buffer.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "xml"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "tr", "td", "th", "div"}:
            self.buffer.append(" ")

    def handle_data(self, data):
        if not self.skip_depth:
            self.buffer.append(data)

    def text(self):
        return normalize_space("".join(self.buffer))


def fetch_phivolcs_html(url=PHIVOLCS_URL):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PQR-Web-App"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except ssl.SSLError:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read().decode("utf-8", "replace")


def fetch_phivolcs_bytes(url):
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
    except urllib.error.URLError as error:
        if "CERTIFICATE_VERIFY_FAILED" not in str(error):
            raise
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read().decode("utf-8", "replace")


def parse_phivolcs_events(html, base_url=PHIVOLCS_URL, limit=50):
    parser = EarthquakeTableParser()
    parser.feed(html)
    events = []
    key_counts = {}
    suffix_counts = {}

    for cells, href in parser.rows:
        if len(cells) < 6 or not looks_like_phivolcs_datetime(cells[0]):
            continue

        try:
            base_event_key = phivolcs_datetime_to_utc_key(cells[0])
            event_datetime_utc = parse_datetime_local_as_utc(cells[0])
        except ValueError:
            continue

        location = clean_location(cells[5])
        key_counts[base_event_key] = key_counts.get(base_event_key, 0) + 1
        suffix_key = (base_event_key, location_suffix(location))
        suffix_counts[suffix_key] = suffix_counts.get(suffix_key, 0) + 1
        events.append(
            PhivolcsEvent(
                ph_time=cells[0],
                event_key=base_event_key,
                event_datetime_utc=event_datetime_utc,
                latitude=parse_float(cells[1]),
                longitude=parse_float(cells[2]),
                depth_km=parse_float(cells[3]),
                magnitude=parse_float(cells[4]),
                reference_location=location,
                region_code=infer_region_code(location),
                source_url=urllib.parse.urljoin(base_url, href.replace("\\", "/")) if href else base_url,
            )
        )

        if len(events) >= limit:
            break

    duplicate_keys = {key for key, count in key_counts.items() if count > 1}
    duplicate_suffixes = {key for key, count in suffix_counts.items() if count > 1}
    suffix_indexes = {}
    for event in events:
        if event.event_key in duplicate_keys:
            suffix = location_suffix(event.reference_location)
            key = (event.event_key, suffix)
            event.event_key = event.event_key + "_" + suffix
            if key in duplicate_suffixes:
                suffix_indexes[key] = suffix_indexes.get(key, 0) + 1
                event.event_key = f"{event.event_key}_{suffix_indexes[key]}"

    return events


def fetch_latest_events(limit=50):
    return parse_phivolcs_events(fetch_phivolcs_html(), limit=limit)


def monthly_archive_url(year, month):
    month_name = MONTH_NAMES[int(month) - 1]
    return f"{PHIVOLCS_URL}EQLatest-Monthly/{int(year)}/{int(year)}_{month_name}.html"


def fetch_monthly_archive_events(year, month, limit=5000):
    url = monthly_archive_url(year, month)
    return parse_phivolcs_events(fetch_phivolcs_html(url), base_url=url, limit=limit)


def phivolcs_url_indicates_felt(url):
    return bool(re.search(r"_B\d+F\.(?:html?|pdf)$", url or "", flags=re.IGNORECASE))


def fetch_recent_events(hours=22, limit=50):
    events = fetch_latest_events(limit=limit)
    return filter_events_within_hours(events, hours)


def filter_events_within_hours(events, hours=22):
    now = utc_now()
    recent = []
    for event in events:
        event_time = parse_utc_iso(event.event_datetime_utc)
        if event_time and (now - event_time).total_seconds() <= hours * 3600:
            recent.append(event)
    return recent


def looks_like_phivolcs_datetime(value):
    return bool(re.search(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s+-\s+\d{1,2}:\d{2}\s+[AP]M", value or ""))


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def clean_intensity_text(value):
    text = normalize_space((value or "").replace("\xa0", " "))
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


def extract_bulletin_intensities(url):
    data = fetch_phivolcs_bytes(url)
    if url.lower().endswith(".pdf"):
        return extract_intensities_from_pdf(data)
    return extract_intensities_from_html(data)


def extract_intensities_from_html(data):
    html = data.decode("utf-8", "replace")
    parser = BulletinCellParser()
    parser.feed(html)
    for cell in [cell for cell in parser.cells if cell and ("Intensit" in cell or re.search(r"\bIntensity\s+[IVX]+", cell))]:
        reported, instrumental = split_intensity_blob(cell)
        if reported or instrumental:
            return reported, instrumental, ""

    text_parser = BulletinTextParser()
    text_parser.feed(html)
    text = text_parser.text()
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
    if start_positions:
        reported, instrumental = split_intensity_blob(text[min(start_positions) :])
        if reported or instrumental:
            return reported, instrumental, ""
    return "", "", "No intensity text found"


def extract_intensities_from_pdf(data):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("PDF intensity extraction requires pypdf.") from error
    reader = PdfReader(io.BytesIO(data))
    text = normalize_space("\n".join(page.extract_text() or "" for page in reader.pages))
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
    return (*split_intensity_blob(text[min(start_positions) :]), "")


def clean_location(value):
    value = normalize_space(value)
    value = value.replace("Â°", "°")
    return value


def parse_float(value):
    value = normalize_space(value)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def location_suffix(location):
    match = re.search(r"\b\d+\s*km\b.*?\bof\s+(.+)$", location or "", flags=re.IGNORECASE)
    text = match.group(1) if match else location
    text = normalize_space(text)
    text = re.sub(r"[^A-Za-z0-9() -]+", "", text or "")
    text = normalize_space(text).strip("- ")
    return text[:80] or "same_time"


def infer_region_code(location):
    text = (location or "").lower()
    province_matches = re.findall(r"\(([^()]*)\)", text)
    province_text = province_matches[-1] if province_matches else ""
    search_texts = [province_text, text] if province_text else [text]
    province_region_overrides = {
        "masbate": "SL",
    }

    for region_text in search_texts:
        for province_name, region_code in province_region_overrides.items():
            if province_name in region_text:
                return region_code

    mindanao_keywords = [
        "agusan",
        "basilan",
        "basila",
        "bukidnon",
        "camiguin",
        "cotabato",
        "davao",
        "dinagat",
        "lanao",
        "maguindanao",
        "misamis",
        "sarangani",
        "south cotabato",
        "sultan kudarat",
        "sulu",
        "surigao",
        "tawi-tawi",
        "tawi tawi",
        "zamboanga",
    ]
    visayas_keywords = [
        "aklan",
        "antique",
        "biliran",
        "bohol",
        "capiz",
        "cebu",
        "guimaras",
        "iloilo",
        "leyte",
        "negros",
        "samar",
        "siquijor",
    ]
    south_luzon_keywords = [
        "albay",
        "batangas",
        "camarines",
        "catanduanes",
        "cavite",
        "laguna",
        "marinduque",
        "mindoro",
        "palawan",
        "quezon",
        "rizal",
        "romblon",
        "sorsogon",
        "masbate",
    ]

    for region_text in search_texts:
        if any(name in region_text for name in mindanao_keywords):
            return "MIN"
        if any(name in region_text for name in visayas_keywords):
            return "VIS"
        if any(name in region_text for name in south_luzon_keywords):
            return "SL"
        if province_text:
            return "NL"
    if any(name in text for name in mindanao_keywords):
        return "MIN"
    if any(name in text for name in visayas_keywords):
        return "VIS"
    if any(name in text for name in south_luzon_keywords):
        return "SL"
    return "NL"
