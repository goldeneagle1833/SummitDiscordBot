"""Turn Explorer applications' preferred event dates into structured rows.

The 2027 apply form asked for "three potential dates" in one free-text box,
so older answers look like "4/10/27, 6/12/27", "Sept 18 or 25" or "mid-June".
`parse()` reads those into date windows with a precision and a confidence;
newer applications pick dates with date pickers and skip the parser.

The rows live in explorer_application_dates. The applicant's own text is
never changed, and once a Council member confirms or fixes the dates for an
application they are never re-parsed over.
"""
import calendar
import re
from datetime import date, timedelta

YEAR = 2027
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
SEASONS = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 10), "autumn": (9, 10)}
PART = {"early": (1, 10), "mid": (11, 20), "middle": (11, 20), "late": (21, 31), "end": (21, 31)}


def _year(y):
    if not y:
        return YEAR, False
    y = int(y)
    return (2000 + y if y < 100 else y), True


def _last(y, m):
    return calendar.monthrange(y, m)[1]


def _win(start, end, precision, confidence, raw):
    return {"start": start.isoformat(), "end": end.isoformat(),
            "precision": precision, "confidence": confidence, "raw": raw.strip()}


def _in_window(d):
    return 3 <= d.month <= 10


def parse(text):
    if not text or not text.strip():
        return []
    s = text.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    out, used = [], []

    def take(m):
        if any(a < m.end() and m.start() < b for a, b in used):
            return False
        used.append((m.start(), m.end()))
        return True

    # 1) Numeric ranges: 4/10-4/11/27 or 4/10-11/27
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*-\s*(?:(\d{1,2})/)?(\d{1,2})(?:/(\d{2,4}))?\b", s):
        mo1, d1, y1, mo2, d2, yy = m.groups()
        yy = yy or y1
        y, has_y = _year(yy)
        try:
            a, b = date(y, int(mo1), int(d1)), date(y, int(mo2 or mo1), int(d2))
        except ValueError:
            continue
        if b >= a and take(m):
            out.append(_win(a, b, "range", "high" if has_y else "medium", m.group()))

    # 2) Numeric single days: 4/10/27, 4/10
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", s):
        mo, d, yy = m.groups()
        y, has_y = _year(yy)
        try:
            dt = date(y, int(mo), int(d))
        except ValueError:
            continue
        if take(m):
            conf = "high" if has_y else "medium"
            if not _in_window(dt):
                conf = "low"
            out.append(_win(dt, dt, "day", conf, m.group()))

    # 3) Month-name day ranges: April 10-11, 2027
    for m in re.finditer(MON + r"\.?\s+(\d{1,2})\s*-\s*(\d{1,2})(?:,?\s*(\d{4}))?", s):
        mon, d1, d2, yy = m.groups()
        y, has_y = _year(yy)
        mo = MONTHS[mon[:4] if mon.startswith("sept") else mon[:3]]
        try:
            a, b = date(y, mo, int(d1)), date(y, mo, int(d2))
        except ValueError:
            continue
        if take(m):
            out.append(_win(a, b, "range", "high" if has_y else "medium", m.group()))

    # 4) Month-name day(s): April 10(, 2027), also "Sept 18 or 25", "May 8 & 15"
    for m in re.finditer(MON + r"\.?\s+(\d{1,2}(?:\s*(?:,|or|and|&|/)\s*\d{1,2}\b(?!/))*)\b(?:,?\s*(\d{4}))?", s):
        mon, days, yy = m.groups()
        y, has_y = _year(yy)
        mo = MONTHS[mon[:4] if mon.startswith("sept") else mon[:3]]
        if not take(m):
            continue
        for d in re.findall(r"\d{1,2}", days):
            try:
                dt = date(y, mo, int(d))
            except ValueError:
                continue
            out.append(_win(dt, dt, "day", "high" if has_y else "medium", f"{mon} {d}"))

    # 5) Part of month: early/mid/late June
    for m in re.finditer(r"\b(early|mid|middle|late|end of)[\s-]*(?:of\s+)?" + MON, s):
        part, mon = m.groups()
        mo = MONTHS[mon[:4] if mon.startswith("sept") else mon[:3]]
        lo, hi = PART[part.split()[0]]
        if take(m):
            out.append(_win(date(YEAR, mo, lo), date(YEAR, mo, min(hi, _last(YEAR, mo))),
                            "week", "low", m.group()))

    # 6) Bare month: June
    for m in re.finditer(r"\b" + MON + r"\b", s):
        mon = m.group(1)
        if mon == "may" and re.search(r"\bmay\s+(be|work|not|have)\b", s[m.start():m.start() + 12]):
            continue  # "may be", "may work"
        mo = MONTHS[mon[:4] if mon.startswith("sept") else mon[:3]]
        if take(m):
            out.append(_win(date(YEAR, mo, 1), date(YEAR, mo, _last(YEAR, mo)),
                            "month", "low", m.group()))

    # 7) Seasons
    for m in re.finditer(r"\b(spring|summer|fall|autumn)\b", s):
        a, b = SEASONS[m.group(1)]
        if take(m):
            out.append(_win(date(YEAR, a, 1), date(YEAR, b, _last(YEAR, b)),
                            "season", "low", m.group()))

    out.sort(key=lambda w: w["start"])
    if not out:
        out.append({"start": None, "end": None, "precision": "unparsed",
                    "confidence": "none", "raw": text.strip()})
    return out

MAX_PICKED_DATES = 3


def parse_picked_dates(values) -> list[date]:
    """Validate the ISO dates sent by the apply form's date pickers.

    Blank entries are skipped, duplicates dropped, order kept. Raises
    ValueError on anything that isn't a real YYYY-MM-DD date.
    """
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise ValueError("Proposed dates must be a list")
    picked = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            day = date.fromisoformat(text[:10])
        except ValueError:
            raise ValueError(f"'{text}' is not a valid date") from None
        if not 2020 <= day.year <= 2100:
            raise ValueError(f"'{text}' is not a valid date")
        if day not in picked:
            picked.append(day)
    if len(picked) > MAX_PICKED_DATES:
        raise ValueError(f"Please choose at most {MAX_PICKED_DATES} dates")
    return picked


def format_picked_dates(days: list[date]) -> str:
    """The text stored in proposed_dates for picked dates: "4/10/27, 6/12/27"."""
    return ", ".join(f"{d.month}/{d.day}/{d.year % 100:02d}" for d in days)


def picked_rows(days: list[date]) -> list[dict]:
    return [
        {"start": d.isoformat(), "end": d.isoformat(), "precision": "day",
         "confidence": "high", "raw": d.isoformat()}
        for d in days
    ]


def rows_for_application(proposed_dates: str | None, picked: list[date] | None = None) -> tuple[list[dict], str]:
    """The date rows for an application and their source ("applicant" or "parser")."""
    if picked:
        return picked_rows(picked), "applicant"
    return parse(proposed_dates or ""), "parser"


def sync_application_dates(repo, application_id: int, picked: list[date] | None = None) -> bool:
    """Rebuild an application's date rows from its current answer.

    Picked dates (date pickers) win; otherwise the free-text proposed_dates
    is parsed. Does nothing once a Council member has confirmed or fixed the
    dates, so their work is never overwritten. Returns True if rows changed.
    """
    if repo.dates_locked(application_id):
        return False
    application = repo.get_application(application_id)
    if not application:
        return False
    text = application.get("proposed_dates") or application.get("proposed_dates_notes") or ""
    rows, source = rows_for_application(text, picked)
    if not text.strip() and not picked:
        rows = []
    repo.replace_dates(application_id, rows, source)
    return True


def backfill_missing_dates(repo=None) -> int:
    """Parse dates for every application that has no date rows yet.

    Runs on startup; cheap and idempotent. Applications with a blank answer
    get no rows and are simply checked again next time.
    """
    if repo is None:
        from repositories.explorer_applications import ExplorerApplicationRepository
        repo = ExplorerApplicationRepository()
    filled = 0
    for application_id in repo.application_ids_without_dates():
        application = repo.get_application(application_id)
        if not (application.get("proposed_dates") or application.get("proposed_dates_notes") or "").strip():
            continue
        sync_application_dates(repo, application_id)
        filled += 1
    return filled
