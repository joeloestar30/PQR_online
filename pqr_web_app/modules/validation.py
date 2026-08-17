import re

VALID_REGIONS = {"NL", "SL", "VIS", "MIN"}
VALID_P_POLARITY = {"iPd", "iPc", "iP", "ePd", "ePc", "eP"}
VALID_S_MARKER = {"eS", "iS"}
VALID_EVENT_TYPE = {"L", "T"}
VALID_REMARKS = {
    "With Phase Reading",
    "No Quake Record",
    "No Data",
    "No Operation",
    "Intensities",
    "No Staff",
    "On Meeting or Lecture or Other Official Business",
    "On Fieldwork",
    "On Leave",
}
ARRIVAL_TIME_RE = re.compile(r"^\d{6}\.\d{2}$")


def clean_text(value):
    return str(value or "").strip()


def optional_float(value):
    value = clean_text(value)
    if not value:
        return None
    return float(value)


def validate_event_form(form):
    errors = []
    if not clean_text(form.get("event_datetime")):
        errors.append("Event date/time is required.")
    if not clean_text(form.get("reference_location")):
        errors.append("Reference location is required.")
    if form.get("region_code") not in VALID_REGIONS:
        errors.append("Region must be NL, SL, VIS, or MIN.")
    return errors


def validate_pqr_form(form):
    return validate_pqr_form_strict(form)


def validate_pqr_form_strict(form):
    errors = []
    if not clean_text(form.get("event_id")):
        errors.append("Earthquake event is required.")
    if not clean_text(form.get("station_id")):
        errors.append("Station is required.")
    if not clean_text(form.get("officer_initials")):
        errors.append("Station officer initials are required.")
    remarks = clean_text(form.get("remarks"))
    if not remarks:
        errors.append("Remarks is required.")
    elif remarks not in VALID_REMARKS:
        errors.append("Remarks value is invalid.")

    p_polarity = clean_text(form.get("p_polarity"))
    if p_polarity and p_polarity not in VALID_P_POLARITY:
        errors.append("P-Polarity must be iPd, iPc, iP, ePd, ePc, or eP.")

    s_marker = clean_text(form.get("s_marker"))
    if s_marker and s_marker not in VALID_S_MARKER:
        errors.append("S must be eS or iS.")

    event_type = clean_text(form.get("event_type"))
    if event_type and event_type not in VALID_EVENT_TYPE:
        errors.append("Type must be L or T.")

    for field, label in [("p_arrival", "P-Arrival"), ("s_arrival", "S-Arrival")]:
        value = clean_text(form.get(field))
        if value and not ARRIVAL_TIME_RE.match(value):
            errors.append(f"{label} must be in HHMMSS.SS format.")

    for field in ["amplitude", "duration"]:
        try:
            optional_float(form.get(field))
        except ValueError:
            errors.append(field.replace("_", " ").title() + " must be numeric.")
    return errors
