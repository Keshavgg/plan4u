"""Multi-currency converter using live rates from Frankfurter (ECB data, no API key)."""
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.app/latest"
REQUEST_TIMEOUT_SECONDS = 8


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> Dict[str, Any]:
    """Converts an amount between two currencies at the latest published rate."""
    from_c = from_currency.upper().strip()
    to_c = to_currency.upper().strip()

    if from_c == to_c:
        return {
            "success": True, "input_amount": amount, "from_currency": from_c, "to_currency": to_c,
            "converted_amount": round(amount, 2), "exchange_rate": 1.0,
        }

    try:
        params = urllib.parse.urlencode({"amount": amount, "from": from_c, "to": to_c})
        req = urllib.request.Request(f"{FRANKFURTER_URL}?{params}", headers={"User-Agent": "Plan4U-App/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        converted = data["rates"][to_c]
        return {
            "success": True,
            "input_amount": amount,
            "from_currency": from_c,
            "to_currency": to_c,
            "converted_amount": round(converted, 2),
            "exchange_rate": round(converted / amount, 4) if amount else None,
            "rate_date": data.get("date"),
        }
    except Exception as e:
        logger.warning("Currency conversion failed (%s->%s): %s", from_c, to_c, e)
        return {"success": False, "error": "Exchange rate service unavailable or currency not supported."}
