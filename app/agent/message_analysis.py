"""One AI call that reads a chat message for everything the copilot needs to know about it.

Before, three separate small AI calls ran one after another on every message (what preferences did the user state,
is this a table booking, what do they want to find). They all read the same message, so they are one call now.
"""
import datetime
import json
import logging
from typing import Any, Dict, Optional

from app.agent.state import CompanionState
from app.agent.subagents.copilot_agent import INTENT_SCHEMA_TEXT, parse_json_object, quick_llm
from app.schemas.agent import LiveCopilotQuery
from app.services.booking_store import booking_store

logger = logging.getLogger(__name__)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HISTORY_TURNS = 6


def analyze(query: LiveCopilotQuery, state: CompanionState, user_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Returns {"memory": {...}, "booking": {...}, "intent": {...}}. Each part is {} if the call failed.

    `state.chat_history` must not yet contain the latest message (it is passed separately).
    """
    now = datetime.datetime.now(IST)
    history = "\n".join(f"{m.role}: {m.content[:300]}" for m in state.chat_history[-HISTORY_TURNS:])
    shown = [p.name for p in state.last_recommended_places][:8]
    contacts = [c["alias"] for c in booking_store.list_contacts(user_id)] if user_id else []

    prompt = (
        "You read a travel-app chat message and extract three things about the LATEST user message. "
        "Reply with ONLY valid JSON, no markdown, no explanation.\n"
        f"Today is {now.strftime('%A %Y-%m-%d')}, the time now is {now.strftime('%H:%M')} (India).\n"
        f"Recent chat:\n{history or '(none)'}\n"
        f"Latest message: \"{query.user_message}\"\n"
        f"Restaurants shown to the user recently: {json.dumps(shown, ensure_ascii=False)}\n"
        f"The user's saved contacts (aliases): {json.dumps(contacts, ensure_ascii=False)}\n\n"
        "JSON schema:\n"
        "{\n"
        " \"memory\": {\"diet\": <\"pure_vegetarian\" | \"non_vegetarian\" | null, only if clearly stated>, "
        "\"budget_tier\": <\"luxury_fine_dining\" | \"budget_friendly\" | null>, "
        "\"vibe\": <\"romantic_date\" | \"party_nightlife\" | \"family_dining\" | null>},\n"
        " \"booking\": {\"book_table\": <true only if the latest message asks to book/reserve a restaurant TABLE "
        "(not event tickets, not food delivery) or continues such a request>, "
        "\"restaurant_name\": <restaurant name exactly as the user or the shown list says; resolve 'the first one' / "
        "'this one' from the shown list; null if unknown>, "
        "\"date\": <YYYY-MM-DD resolved from today (kal=tomorrow, parso=day after), null if not stated>, "
        "\"time\": <24h HH:MM, null if not stated>, "
        "\"guests\": <integer, null if not stated>, "
        "\"for_contact\": <one saved contact alias if the user is booking for that person, else null>},\n"
        f" \"intent\": {INTENT_SCHEMA_TEXT}\n"
        "}"
    )

    try:
        parsed = parse_json_object(quick_llm(prompt))
    except Exception as e:
        logger.warning("Message analysis failed: %s", e)
        return {"memory": {}, "booking": {}, "intent": {}}

    def part(name: str) -> Dict[str, Any]:
        value = parsed.get(name)
        return value if isinstance(value, dict) else {}

    return {"memory": part("memory"), "booking": part("booking"), "intent": part("intent")}
