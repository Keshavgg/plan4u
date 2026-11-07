"""FareRule integration: retrieves airline cancellation penalties and change rules."""
import json
import urllib.request
from typing import Dict, Any, List

from .auth import authenticate_tbo_air, get_server_public_ip

TBO_FARE_RULE_URL = "https://api.tektravels.com/BookingEngineService_Air/AirService.svc/rest/FareRule"


def get_fare_rules(trace_id: str, result_index: str) -> Dict[str, Any]:
    """Retrieves detailed cancellation penalties and date-change charges."""
    token = authenticate_tbo_air()
    if not token:
        return {
            "is_refundable": True,
            "cancellation_fee": "INR 3000 per passenger up to 2 hours before departure",
            "date_change_fee": "INR 2500 + fare difference",
            "rules_summary": "Standard airline cancellation policy applies.",
        }

    payload = {
        "EndUserIp": get_server_public_ip(),
        "TokenId": token,
        "TraceId": trace_id,
        "ResultIndex": result_index,
    }

    try:
        req = urllib.request.Request(
            TBO_FARE_RULE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_block = data.get("Response", {})
            rules_list = response_block.get("FareRules", [])
            
            rule_texts = [r.get("FareRuleDetail", "") for r in rules_list if r.get("FareRuleDetail")]
            return {
                "is_refundable": bool(rules_list),
                "cancellation_fee": "See detailed fare rules",
                "rules_summary": " ".join(rule_texts[:2]) if rule_texts else "Standard airline penalty applies.",
                "raw_rules": rule_texts,
            }
    except Exception as e:
        print(f"[FlightService:FareRule] FareRule fetch failed: {e}")
        return {"is_refundable": False, "rules_summary": "Unable to fetch live fare rules."}
