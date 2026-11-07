"""Date helpers for endpoints where the caller may omit stay/travel dates."""
import datetime
from typing import Optional, Tuple


def resolve_stay_dates(
    check_in: Optional[str],
    check_out: Optional[str],
    start_offset_days: int = 1,
    nights: int = 2,
) -> Tuple[str, str]:
    """Return (check_in, check_out) as YYYY-MM-DD, defaulting relative to today when omitted."""
    today = datetime.date.today()
    start = check_in or (today + datetime.timedelta(days=start_offset_days)).isoformat()
    if check_out:
        return start, check_out
    start_date = datetime.date.fromisoformat(start)
    return start, (start_date + datetime.timedelta(days=nights)).isoformat()
