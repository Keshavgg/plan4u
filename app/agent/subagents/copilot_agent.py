"""Live City Copilot Subagent (Panel 2: On-Trip Real-Time Concierge) powered by Claude Sonnet & Gemini AI."""
from typing import Optional, List, Dict, Any, Tuple
import functools
import json
import re
import urllib.parse
import uuid
from app.config import settings
from app.schemas.agent import (
    LiveCopilotQuery,
    LiveCopilotResponse,
    LiveCopilotActionType,
    AgentRole,
    ChatMessage,
)
from app.schemas.attraction import PlaceItem, GeoLocation, PlaceCategory, PriceBand
from app.tools.dining import search_restaurants_tool, search_cafes_tool
from app.tools.events import search_live_events_tool
from app.tools.attractions import search_attractions_tool
from app.tools.payments import create_checkout_session_tool
from app.services.smart_tools.emergency_reroute import get_emergency_reroute_options
from app.services.smart_tools.transport_estimator import estimate_transport_options
from app.tools.registry import get_tools_for_agent
from app.agent.prompts import LIVE_COPILOT_PROMPT

# How many cards a chat answer can carry, and how many restaurants the model is told about.
SWIGGY_CARD_LIMIT = 12          # restaurants taken from the cached Swiggy search
SWIGGY_FOOD_CARD_LIMIT = 8      # food-delivery cards (shown as ticket-style cards)
MAX_PLACE_CARDS = 12            # place cards in one response
EVENT_CARD_LIMIT = 8            # event / movie cards in one response
PROMPT_RESTAURANT_LINES = 8     # keeps the prompt short; the cards still show every restaurant


def extract_clean_copilot_payload(raw_ai: str) -> Dict[str, Any]:
    """Guarantees raw JSON or raw keys like 'reply_text': never leak to user."""
    if not raw_ai:
        return {}

    text = raw_ai.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # 1. Attempt standard JSON parsing on matched outer braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_candidate = text[start:end + 1]
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, dict):
                r_text = parsed.get("reply_text")
                # Handle double-encoded JSON if model nested it
                if isinstance(r_text, str) and r_text.strip().startswith("{"):
                    try:
                        inner = json.loads(r_text.strip())
                        if isinstance(inner, dict) and "reply_text" in inner:
                            parsed["reply_text"] = inner["reply_text"]
                            if "places" in inner and not parsed.get("places"):
                                parsed["places"] = inner["places"]
                    except Exception:
                        pass
                
                if parsed.get("reply_text"):
                    clean_reply = str(parsed["reply_text"]).replace("\\n", "\n").replace('\\"', '"').strip()
                    # Strip any leftover prefix or quotes
                    for prefix in ['{"reply_text":', '{"reply_text" :', '{"reply_text"', '"reply_text":', 'reply_text:']:
                        if clean_reply.startswith(prefix):
                            clean_reply = clean_reply[len(prefix):].strip()
                    if clean_reply.startswith('"') and clean_reply.endswith('"') and len(clean_reply) > 2:
                        clean_reply = clean_reply[1:-1].strip()
                    parsed["reply_text"] = clean_reply
                    return parsed
        except Exception:
            pass

    # 2. Resilient regex extraction if JSON had trailing truncation or unescaped quotes
    reply_text = ""
    # Regex matching reply_text up to next JSON key
    m_reply = re.search(r'"reply_text"\s*:\s*"(.*?)(?:"\s*,\s*"(?:action_type|should_show_cards|places|ticket_card|quick_replies)"|\s*"\s*\})', text, re.DOTALL)
    if m_reply:
        reply_text = m_reply.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
    else:
        # Fallback strip prefix and suffix
        clean = text
        clean = re.sub(r'^\s*\{\s*"reply_text"\s*:\s*"?', '', clean)
        clean = re.sub(r'^\s*"reply_text"\s*:\s*"?', '', clean)
        clean = re.sub(r'"?\s*\}\s*$', '', clean)
        clean = clean.replace('\\n', '\n').replace('\\"', '"').strip()
        if clean.endswith('"'):
            clean = clean[:-1]
        reply_text = clean

    # Strip any accidental leftover quotes or keys
    for prefix in ['{"reply_text":', '"reply_text":', 'reply_text:']:
        if reply_text.startswith(prefix):
            reply_text = reply_text[len(prefix):].strip()
    if reply_text.startswith('"') and reply_text.endswith('"') and len(reply_text) > 2:
        reply_text = reply_text[1:-1].strip()

    # Extract action_type
    action_type = "general_chat"
    m_action = re.search(r'"action_type"\s*:\s*"([^"]+)"', text)
    if m_action:
        action_type = m_action.group(1)

    # Extract places array
    places = []
    m_places = re.search(r'"places"\s*:\s*(\[\s*\{.*?\}\s*\])', text, re.DOTALL)
    if m_places:
        try:
            places = json.loads(m_places.group(1))
        except Exception:
            pass

    # Extract quick_replies
    quick_replies = []
    m_qr = re.search(r'"quick_replies"\s*:\s*(\[[^\]]*\])', text, re.DOTALL)
    if m_qr:
        try:
            quick_replies = json.loads(m_qr.group(1))
        except Exception:
            pass

    return {
        "reply_text": reply_text,
        "action_type": action_type,
        "should_show_cards": len(places) > 0,
        "places": places,
        "quick_replies": quick_replies or ["Where to go next? 🗺️", "Food options nearby 🍽️", "Live events 🎸"],
    }


@functools.lru_cache(maxsize=1)
def _gemini_client():
    """One shared Gemini client. Creating one takes about 4 s, so it must not happen on every call."""
    from google import genai
    return genai.Client(api_key=settings.GEMINI_API_KEY)


@functools.lru_cache(maxsize=1)
def _anthropic_client():
    """One shared Anthropic client (creating a client per call is slow)."""
    import anthropic
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def quick_llm(prompt: str) -> Optional[str]:
    """Short, cheap completion for classification and extraction (Gemini flash-lite first).

    Falls back to the main engine if Gemini is unavailable. Returns None if nothing answered.
    """
    if settings.GEMINI_API_KEY:
        try:
            from google import genai
            client = _gemini_client()
            from google.genai import types
            fast = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),  # classification does not need reasoning
                max_output_tokens=600,
            )
            for model in ("gemini-3.5-flash-lite", "gemini-3.5-flash"):
                try:
                    try:
                        resp = client.models.generate_content(model=model, contents=prompt, config=fast)
                    except Exception:  # this model may not accept the thinking setting
                        resp = client.models.generate_content(model=model, contents=prompt)
                    if resp.text and resp.text.strip():
                        return resp.text.strip()
                except Exception:
                    continue
        except Exception as e:
            print(f"[Copilot:QuickLLM] Warning: {e}")
    return call_ai_engine(prompt)


def parse_json_object(raw: Optional[str]) -> Dict[str, Any]:
    """Pulls the first JSON object out of an LLM reply, tolerating code fences. {} if there is none."""
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


# JSON shape the copilot needs to know about a message (reused by the combined message analysis).
INTENT_SCHEMA_TEXT = (
    "{\"food_or_dining\": <true ONLY if the user asks for food, a restaurant/cafe/dhaba, a dish or a cuisine; false for general plans such as 'what to do tonight' or 'weekend plan'>, "
    "\"delivery\": <true if user explicitly wants home delivery or online food order, NOT dine-in>, "
    "\"events\": <true if user wants a live event, concert, comedy show, nightlife, club or any ticketed experience, OR asks open-endedly what to do or for a plan tonight / this weekend>, "
    "\"movies\": <true if user wants to watch a movie at a cinema/theatre>, "
    "\"event_query\": <when events or movies is true: a category word (comedy, music, nightlife, theatre, festival, workshop, sports, art, movie) and/or a specific artist or event name, for example 'comedy', 'zakir khan', 'pottery workshop'; null for open-ended asks like 'what to do tonight'>, "
    
    "\"search_term\": <ONE or TWO words describing the KIND of place to search a restaurant app with: a cuisine, place type or vibe, "
    "such as 'cafe', 'biryani', 'rooftop', 'fine dining', 'romantic'. Never a meal time like 'dinner', 'lunch' or 'breakfast' "
    "(the app matches restaurant NAMES), and never a taste or adjective such as 'spicy' or 'tasty': pick the cuisine that fits (spicy -> 'north indian', sweet -> 'desserts'). Use 'restaurant' if nothing more specific. "
    "No location words, no full sentence; null if food_or_dining is false>}"
)

# Used only when the combined analysis did not provide an intent (for example if that call failed).
INTENT_FALLBACK = {"food_or_dining": True, "delivery": False, "events": True, "movies": False}


def classify_intent(user_msg: str, hist_text: str) -> Dict[str, Any]:
    """Stand-alone intent classification (one AI call)."""
    prompt = (
        "Classify the user's intent from this message and recent chat context. "
        "Reply with ONLY valid JSON, no markdown, no explanation.\n"
        f"Message: \"{user_msg}\"\n"
        f"Recent context: \"{hist_text[-300:]}\"\n\n"
        f"JSON schema (all fields required):\n{INTENT_SCHEMA_TEXT}"
    )
    try:
        intent = parse_json_object(quick_llm(prompt))
        if intent:
            return intent
        raise ValueError("classifier returned no JSON")
    except Exception as e:
        print(f"[CopilotAgent] Intent classification fallback: {e}")
        return dict(INTENT_FALLBACK)


def call_ai_engine(
    prompt: str,
    system_prompt: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Optional[str]:
    """Generates real-time AI response using Claude Sonnet 5.5 and Gemini multi-model pool.
    
    Full multi-turn conversation memory. Zero regex intent locks, zero dummy data.
    """
    # 1. Primary: Anthropic Claude Sonnet 5.5
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic
            client_a = _anthropic_client()
            model_a = getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5-5")

            messages: List[Dict[str, str]] = []
            if conversation_history:
                for turn in conversation_history[-8:]:
                    r = turn.get("role", "user")
                    c = turn.get("content", "").strip()
                    if c:
                        messages.append({
                            "role": "user" if r == "user" else "assistant",
                            "content": c
                        })

            # Prevent consecutive user messages at the end
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] = prompt
            else:
                messages.append({"role": "user", "content": prompt})

            kwargs: Dict[str, Any] = {
                "model": model_a,
                "max_tokens": 4000,
                "messages": messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            msg = client_a.messages.create(**kwargs)
            for block in msg.content:
                if getattr(block, "type", None) == "text" and hasattr(block, "text") and block.text:
                    print(f"[Copilot:Claude] Generated high-fidelity response using {model_a}")
                    return block.text.strip()
        except Exception as e:
            print(f"[Copilot:Claude] Warning: {e}")

    # 2. Secondary: Google Gemini (High Performance Flash Pool)
    if settings.GEMINI_API_KEY:
        try:
            from google import genai
            client = _gemini_client()
            models = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]

            hist_str = ""
            if conversation_history:
                hist_str = "Prior Conversation History in this active session:\n"
                for turn in conversation_history[-8:]:
                    speaker = "Traveler" if turn.get("role") == "user" else "Copilot"
                    hist_str += f"{speaker}: {turn.get('content', '')}\n"
                hist_str += "\n"

            contents = f"{system_prompt}\n\n{hist_str}{prompt}" if system_prompt else f"{hist_str}{prompt}"
            for m in models:
                try:
                    resp = client.models.generate_content(model=m, contents=contents)
                    if resp.text and resp.text.strip():
                        return resp.text.strip()
                except Exception:
                    continue
        except Exception as e:
            print(f"[Copilot:Gemini] Warning: {e}")

    return None


LOCALITY_REGISTRY: Dict[str, Tuple[str, float, float]] = {
    # Delhi & NCR - Dwarka Sectors & Markets (All 1-24)
    "dwarka sector 14": ("Delhi", 28.5921, 77.0250),
    "dwarka sec 14": ("Delhi", 28.5921, 77.0250),
    "dwarka 14": ("Delhi", 28.5921, 77.0250),
    "dwarka sector 24": ("Delhi", 28.5520, 77.0120),
    "dwarka sec 24": ("Delhi", 28.5520, 77.0120),
    "dwarka 24": ("Delhi", 28.5520, 77.0120),
    "dwarka sector 13": ("Delhi", 28.5980, 77.0320),
    "dwarka sec 13": ("Delhi", 28.5980, 77.0320),
    "dwarka 13": ("Delhi", 28.5980, 77.0320),
    "dwarka sector 12": ("Delhi", 28.5925, 77.0400),
    "dwarka sec 12": ("Delhi", 28.5925, 77.0400),
    "dwarka 12": ("Delhi", 28.5925, 77.0400),
    "dwarka sector 10": ("Delhi", 28.5815, 77.0540),
    "dwarka sec 10": ("Delhi", 28.5815, 77.0540),
    "dwarka 10": ("Delhi", 28.5815, 77.0540),
    "dwarka sector 7": ("Delhi", 28.5830, 77.0650),
    "dwarka sec 7": ("Delhi", 28.5830, 77.0650),
    "dwarka 7": ("Delhi", 28.5830, 77.0650),
    "ramphal chowk": ("Delhi", 28.5830, 77.0650),
    "dwarka sector 6": ("Delhi", 28.5890, 77.0600),
    "dwarka sec 6": ("Delhi", 28.5890, 77.0600),
    "dwarka 6": ("Delhi", 28.5890, 77.0600),
    "dwarka sector 11": ("Delhi", 28.5890, 77.0480),
    "dwarka sec 11": ("Delhi", 28.5890, 77.0480),
    "dwarka 11": ("Delhi", 28.5890, 77.0480),
    "pitampura": ("Delhi", 28.7033, 77.1325),
    "nsp": ("Delhi", 28.6980, 77.1510),
    "netaji subhash place": ("Delhi", 28.6980, 77.1510),
    "vegas mall": ("Delhi", 28.5921, 77.0250),
    "dwarka mor": ("Delhi", 28.6180, 77.0320),
    "dwarka": ("Delhi", 28.5921, 77.0460),

    # Delhi Other Landmarks
    "rohini": ("Delhi", 28.7041, 77.1025),
    "kamla nagar": ("Delhi", 28.6800, 77.2050),
    "connaught place": ("Delhi", 28.6315, 77.2167),
    "cp": ("Delhi", 28.6315, 77.2167),
    "hauz khas": ("Delhi", 28.5494, 77.2001),
    "hkv": ("Delhi", 28.5494, 77.2001),
    "lajpat nagar": ("Delhi", 28.5700, 77.2400),
    "sarojini nagar": ("Delhi", 28.5750, 77.1980),
    "khan market": ("Delhi", 28.6000, 77.2270),
    "south extension": ("Delhi", 28.5710, 77.2210),
    "south ex": ("Delhi", 28.5710, 77.2210),
    "saket": ("Delhi", 28.5245, 77.2066),
    "karol bagh": ("Delhi", 28.6514, 77.1907),
    "chandni chowk": ("Delhi", 28.6506, 77.2303),
    "jama masjid": ("Delhi", 28.6506, 77.2334),
    "qutub minar": ("Delhi", 28.5245, 77.1855),
    "red fort": ("Delhi", 28.6562, 77.2410),
    "aerocity": ("Delhi", 28.5490, 77.1210),
    "noida": ("Delhi", 28.5355, 77.3910),
    "gurgaon": ("Delhi", 28.4595, 77.0266),
    "gurugram": ("Delhi", 28.4595, 77.0266),
    "delhi": ("Delhi", 28.6139, 77.2090),

    # Mumbai
    "colaba": ("Mumbai", 18.9067, 72.8147),
    "bandra": ("Mumbai", 19.0596, 72.8295),
    "andheri": ("Mumbai", 19.1136, 72.8697),
    "juhu": ("Mumbai", 19.0988, 72.8264),
    "marine drive": ("Mumbai", 18.9432, 72.8230),
    "dadar": ("Mumbai", 19.0178, 72.8478),
    "gateway of india": ("Mumbai", 18.9220, 72.8347),
    "mumbai": ("Mumbai", 19.0760, 72.8777),

    # Goa
    "calangute": ("Goa", 15.5440, 73.7554),
    "baga": ("Goa", 15.5520, 73.7517),
    "anjuna": ("Goa", 15.5870, 73.7420),
    "vagator": ("Goa", 15.6028, 73.7336),
    "panjim": ("Goa", 15.4909, 73.8278),
    "candolim": ("Goa", 15.5180, 73.7680),
    "morjim": ("Goa", 15.6322, 73.7380),
    "siolim": ("Goa", 15.6212, 73.7656),
    "goa": ("Goa", 15.5180, 73.7680),

    # Jaipur
    "amber fort": ("Jaipur", 26.9855, 75.8513),
    "amer": ("Jaipur", 26.9855, 75.8513),
    "hawa mahal": ("Jaipur", 26.9239, 75.8267),
    "pink city": ("Jaipur", 26.9239, 75.8267),
    "johari": ("Jaipur", 26.9205, 75.8240),
    "c-scheme": ("Jaipur", 26.9080, 75.8010),
    "malviya nagar": ("Jaipur", 26.8520, 75.8150),
    "jaipur": ("Jaipur", 26.9124, 75.8270),

    # Bengaluru
    "koramangala": ("Bengaluru", 12.9352, 77.6245),
    "indiranagar": ("Bengaluru", 12.9784, 77.6408),
    "whitefield": ("Bengaluru", 12.9698, 77.7500),
    "mg road": ("Bengaluru", 12.9756, 77.6066),
    "bangalore": ("Bengaluru", 12.9716, 77.5946),
    "bengaluru": ("Bengaluru", 12.9716, 77.5946),

    # Hyderabad
    "charminar": ("Hyderabad", 17.3616, 78.4747),
    "hitec city": ("Hyderabad", 17.4435, 78.3772),
    "jubilee hills": ("Hyderabad", 17.4319, 78.4073),
    "hyderabad": ("Hyderabad", 17.3850, 78.4867),

    # Udaipur, Agra, Kolkata, Chennai, Kochi
    "udaipur": ("Udaipur", 24.5854, 73.7125),
    "taj mahal": ("Agra", 27.1751, 78.0421),
    "agra": ("Agra", 27.1767, 78.0081),
    "kolkata": ("Kolkata", 22.5726, 88.3639),
    "chennai": ("Chennai", 13.0827, 80.2707),
    "kochi": ("Kochi", 9.9312, 76.2673),
}


class LiveCopilotAgent:
    """Specialist subagent acting as an on-the-ground local friend, real-time fixer, and emergency concierge."""

    def __init__(self):
        self.role = AgentRole.LIVE_CITY_COPILOT
        self.authorized_tools = get_tools_for_agent(self.role)

    def resolve_location(
        self,
        user_msg: str,
        query_lat: float,
        query_lng: float,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, str, float, float]:
        """Resolves city, locality name, and coordinates using exact substring match or prior turns."""
        msg_low = user_msg.lower()

        # Check exact matches in registry (longest matched phrase first)
        sorted_locs = sorted(LOCALITY_REGISTRY.keys(), key=lambda k: len(k), reverse=True)
        for loc in sorted_locs:
            if loc in msg_low:
                city, lat, lng = LOCALITY_REGISTRY[loc]
                return city, loc.title(), lat, lng

        # If not in current message, check conversation history (from most recent turn backwards)
        if conversation_history:
            for turn in reversed(conversation_history):
                c_low = turn.get("content", "").lower()
                for loc in sorted_locs:
                    if loc in c_low:
                        city, lat, lng = LOCALITY_REGISTRY[loc]
                        return city, loc.title(), lat, lng

        # Fallback to GPS coordinates via Real-Time Reverse Geocoding
        lat, lng = query_lat, query_lng
        try:
            from app.services.location_service import reverse_geocode_coords
            geo_info = reverse_geocode_coords(lat, lng)
            if geo_info.get("city") and geo_info.get("locality"):
                return geo_info["city"], geo_info["locality"], lat, lng
        except Exception:
            pass

        if 28.3 <= lat <= 28.9 and 76.8 <= lng <= 77.5:
            return "Delhi", "Delhi NCR", lat, lng
        elif 18.8 <= lat <= 19.4 and 72.7 <= lng <= 73.1:
            return "Mumbai", "Mumbai", lat, lng
        elif 14.8 <= lat <= 16.0 and 73.5 <= lng <= 74.3:
            return "Goa", "Goa", lat, lng
        elif 26.7 <= lat <= 27.2 and 75.6 <= lng <= 76.0:
            return "Jaipur", "Jaipur", lat, lng
        elif 12.8 <= lat <= 13.2 and 77.4 <= lng <= 77.8:
            return "Bengaluru", "Bengaluru", lat, lng
        elif 17.2 <= lat <= 17.6 and 78.3 <= lng <= 78.6:
            return "Hyderabad", "Hyderabad", lat, lng
        elif 24.4 <= lat <= 24.8 and 73.6 <= lng <= 73.8:
            return "Udaipur", "Udaipur", lat, lng
        elif 27.0 <= lat <= 27.3 and 77.9 <= lng <= 78.2:
            return "Agra", "Agra", lat, lng
        elif 22.4 <= lat <= 22.8 and 88.2 <= lng <= 88.5:
            return "Kolkata", "Kolkata", lat, lng
        elif 12.9 <= lat <= 13.2 and 80.1 <= lng <= 80.4:
            return "Chennai", "Chennai", lat, lng
        elif 9.8 <= lat <= 10.2 and 76.1 <= lng <= 76.4:
            return "Kochi", "Kochi", lat, lng

        return "Delhi", "Current Location", lat, lng

    @staticmethod
    def generate_booking_url(provider: str, title: str, fallback_url: Optional[str] = None, city: str = "Delhi") -> str:
        # Never allow broken or 403-blocked BookMyShow explore/search links
        if fallback_url and fallback_url.startswith("http") and "explore/search" not in fallback_url:
            return fallback_url

        p_low = (provider or "").lower()
        clean_title = (title or "").strip()
        encoded_query = urllib.parse.quote(clean_title)
        encoded_city = urllib.parse.quote(city)
        city_slug = re.sub(r'[^a-z0-9]+', '-', (city or "delhi").lower()).strip('-') or "delhi"
        
        if "swiggy dineout" in p_low or "dineout" in p_low:
            from app.services.swiggy_mcp_service import swiggy_mcp_service
            return swiggy_mcp_service.resolve_restaurant_dineout_url(clean_title, city)
        elif "swiggy" in p_low or "instamart" in p_low:
            return f"https://www.swiggy.com/search?query={encoded_query}" if clean_title else "https://www.swiggy.com"
        elif "district" in p_low:
            return f"https://www.district.in/search?q={encoded_query}" if clean_title else "https://www.district.in/events"
        elif "insider" in p_low or "paytm" in p_low:
            return f"https://insider.in/search?q={encoded_query}" if clean_title else f"https://insider.in/{city_slug}"
        elif "zomato" in p_low:
            return "https://www.zomato.com/district"
        elif "skillbox" in p_low:
            return f"https://www.skillbox.co/search?q={encoded_query}" if clean_title else "https://www.skillbox.co"
        elif "venue" in p_low or "door" in p_low:
            return f"https://www.google.com/search?q={urllib.parse.quote(clean_title + ' ' + city + ' tickets venue')}"
        else:  # BookMyShow or default
            # Direct BookMyShow search endpoints trigger Cloudflare 403 Forbidden.
            # Routing via Google search targeting BookMyShow showtimes guarantees reliable, unblocked landing.
            return f"https://www.google.com/search?q=bookmyshow+{encoded_query}+{encoded_city}+tickets" if clean_title else f"https://in.bookmyshow.com/explore/movies-{encoded_city.lower()}"

    def run(self, query: LiveCopilotQuery, user_memory: Optional[Dict[str, Any]] = None,
            user_id: Optional[str] = None,
            precomputed_intent: Optional[Dict[str, Any]] = None) -> LiveCopilotResponse:
        user_msg = query.user_message.strip()

        # Step 1: Multi-Turn Conversation History Formatter
        history_turns: List[Dict[str, str]] = []
        if query.conversation_history:
            for item in query.conversation_history:
                history_turns.append({"role": item.role, "content": item.content})

        # Format Persistent User Memory
        memory_context = ""
        if user_memory:
            facts = user_memory.get("facts", {})
            recollections = user_memory.get("recollections", [])
            facts_lines = [f"- {k}: {v}" for k, v in facts.items()]
            rec_lines = [f"- {r.get('topic')}: {r.get('content')} (confidence {r.get('confidence', 0.8)})" for r in recollections]
            if facts_lines or rec_lines:
                memory_context = "\n[PERSISTENT USER PROFILE & MEMORY (Strict Truth)]\n"
                if facts_lines:
                    memory_context += "CONFIRMED USER FACTS:\n" + "\n".join(facts_lines) + "\n"
                if rec_lines:
                    memory_context += "INFERRED PREFERENCES:\n" + "\n".join(rec_lines) + "\n"
                memory_context += "CRITICAL: You MUST strictly honor confirmed user facts (e.g., if diet is pure_vegetarian, NEVER recommend non-veg; if budget_tier is luxury_fine_dining, NEVER suggest budget sweet shops or casual buffets; if vibe is romantic_date, suggest candle-light/lounge luxury)!\n"

        # Step 2: Accurate City and Locality Resolution (Zero regex, memory aware)
        city, locality, lat, lng = self.resolve_location(user_msg, query.current_lat, query.current_lng, history_turns)

        # Step 3: LLM-based intent classification — zero hardcoded keyword lists
        msg_low = user_msg.lower()
        hist_text = " ".join([h.get("content", "").lower() for h in history_turns[-3:]])
        full_context_low = f"{msg_low} {hist_text}"

        # The intent normally arrives already analysed (together with the booking and memory checks);
        # classify here only if it did not.
        intent: Dict[str, Any] = dict(precomputed_intent or {}) or classify_intent(user_msg, hist_text)

        # Swiggy's search takes a short term (cuisine, place type), not the user's whole sentence.
        swiggy_term = str(intent.get("search_term") or "").strip()[:40] or "restaurant"
        is_movie_query = bool(intent.get("movies", False))
        is_events_query = bool(intent.get("events", False)) or is_movie_query

        live_events_context = ""
        events_list: List[Dict[str, Any]] = []
        top_event = None
        if is_events_query:
            try:
                # What to look for comes from the analysis; None means "browse what is on".
                cat_to_pass = str(intent.get("event_query") or "").strip() or ("movie" if is_movie_query else None)
                events_data = search_live_events_tool(city=city, locality=locality, category=cat_to_pass, lat=lat, lng=lng)
                events_list = events_data.get("events", [])
                if events_list:
                    top_event = events_list[0]
                    live_events_context = f"\nVerified Live Events / Movies in {city}:\n"
                    for idx, ev in enumerate(events_list[:5]):
                        provider = ev.get("booking_provider")
                        title = ev.get("title") or ""
                        url = self.generate_booking_url(provider, title, ev.get("booking_url"), city=city)
                        ev["booking_url"] = url
                        # Fields Exa did not provide are None; say so instead of printing "None" or inventing a value.
                        live_events_context += (
                            f"{idx+1}. '{title}' at {ev.get('venue') or 'venue not listed'} "
                            f"({ev.get('date_time') or 'date not listed'}) | "
                            f"Price: {ev.get('price_range_inr') or 'not listed'} | "
                            f"Ticketing App / Partner: {provider or 'not listed'} | Booking Link: {url}\n"
                        )
            except Exception as ex:
                print(f"[EventsTool] Warning: {ex}")

        # Step 3.5: Direct Swiggy MCP / Live Engine for All Food & Restaurant Searches (Zero Exa)
        # Intent flags come from the LLM classification done above — zero hardcoded keyword lists
        is_delivery_explicit = bool(intent.get("delivery", False))
        is_dining_or_food_query = bool(intent.get("food_or_dining", False))

        swiggy_context = ""
        swiggy_cards: List[Dict[str, Any]] = []
        if is_dining_or_food_query and lat is not None and lng is not None:
            try:
                from app.services.swiggy_mcp_service import SwiggyAuthRequired, SwiggyError
                from app.services.swiggy_search_cache import swiggy_search_cache
                area = locality or city
                # Results come from a shared cache (refreshed in the background every few hours); a Swiggy search
                # only happens on a miss, using the user's own account if connected, else the service account.
                if is_delivery_explicit:
                    f_results = swiggy_search_cache.search(user_id, "food", swiggy_term, lat, lng, limit=SWIGGY_CARD_LIMIT)
                    for item in f_results:
                        swiggy_cards.append({
                            "id": item["id"],
                            "title": f"Order {item['name']}",
                            "category": "food_delivery",
                            "venue": f"Swiggy Delivery • {item.get('locality') or area}",
                            "date_time": f"Delivers in {item['sla_string']}" if item.get("sla_string") else None,
                            "price_range": item.get("cost_for_two"),
                            "booking_url": item["order_url"],
                            "provider": "Swiggy",
                            "description": f"Cuisines: {', '.join(item.get('cuisines', []))}",
                        })
                    if swiggy_cards:
                        swiggy_context = f"\nLive Swiggy Food Delivery options near {area} (Swiggy MCP):\n"
                        for idx, sc in enumerate(swiggy_cards[:PROMPT_RESTAURANT_LINES]):
                            swiggy_context += f"{idx+1}. {sc['title']} | Delivery: {sc['date_time']} | Cost: {sc['price_range']} | Area: {sc['venue']}\n"
                else:
                    d_results = swiggy_search_cache.search(user_id, "dineout", swiggy_term, lat, lng, limit=SWIGGY_CARD_LIMIT)
                    for item in d_results:
                        swiggy_cards.append({
                            "id": item["id"],
                            "title": f"Dineout: {item['name']}",
                            "name": item["name"],
                            "category": "table_reservation",
                            "venue": f"{item['name']} • {item.get('locality') or area}",
                            "date_time": item.get("discount_text"),
                            "price_range": item.get("discount_text"),
                            "booking_url": item["booking_url"],
                            "provider": "Swiggy Dineout",
                            "cost_per_person": item.get("cost_per_person"),
                            "rating": item.get("rating"),
                            "cuisines": item.get("cuisines", []),
                            "description": f"Cuisines: {', '.join(item.get('cuisines', []))}",
                            "is_bookable": True
                        })
                    if swiggy_cards:
                        swiggy_context = f"\nLive Swiggy Dineout restaurants near {area} (Swiggy MCP):\n"
                        for idx, sc in enumerate(swiggy_cards[:PROMPT_RESTAURANT_LINES]):
                            swiggy_context += (
                                f"{idx+1}. {sc['name']} | Area: {sc['venue']} | Rating: {sc['rating']} | "
                                f"Cost per person: {sc['cost_per_person']} | Offer: {sc['price_range']} | {sc['description']}\n"
                            )
            except SwiggyAuthRequired:
                print("[SwiggyMCP] Skipped: Swiggy account is not connected.")
            except SwiggyError as ex:
                print(f"[SwiggyMCP] Copilot query failed: {ex}")
            except Exception as ex:
                print(f"[SwiggyMCP] Copilot query integration error: {ex}")

        # Step 4: Prompt for Claude Sonnet 5.5 / Gemini
        ai_prompt = f"""
You are Plan4U Live Copilot (Panel 2: On-Trip Real-Time Concierge & Local Buddy).
You are an intelligent, street-smart local friend who knows the ground reality of Indian cities ({city}, near {locality}).
You have full memory of the conversation. When the user sends a follow-up (e.g. 'kal 2pm ko hai', 'budget ₹500 hai', 'ye oen time bta kal hai date 4pm ko', 'aur batao'), ALWAYS connect it to the ongoing topic discussed in the conversation history!
Device Context: Active Location: City={city}, Locality={locality}, Time: {query.current_time_str}.
{memory_context}
{live_events_context}
{swiggy_context}

User Message: "{user_msg}"

Determine the optimal response:
1. SPECIFIC SHOP / STALL VERIFICATION (e.g. 'koi lokesh momos wala hai dwarka sec 14 mai', 'dolma aunty lajpat nagar mein kahan hai'):
   - Answer directly and factually whether that specific shop exists at that exact sector/area.
   - For example, if asked about 'Lokesh Momos' in Dwarka Sec 14:
     Point out that 'Lokesh Hot Momos' in Dwarka is famously located in Sector 7 (Ramphal Chowk), NOT Sector 14!
     In Sector 14, you have Vegas Mall & Metro Station stalls (like KC Momos, Hungry Birds, Wow Momo).
     Recommend both: where to go in Sec 14 right now vs heading to Ramphal Chowk Sec 7 for the real Lokesh momos experience.
   - Set "should_show_cards": true and include places (e.g. Lokesh Hot Momos Sec 7, Hungry Birds Sec 14, etc.) in "places".

2. CONTINUOUS CONVERSATION & CARD PERSISTENCE:
   - Answer directly and conversationally in authentic, friendly Hinglish.
   - Connect naturally to earlier discussion (e.g. date time, budget, person count, location).
   - CRITICAL CARD RULE: Whenever your response mentions, suggests, compares, or provides timings for specific venues/spots (e.g. The Great Kabab Factory, Cafe Delhi Heights, Third Wave Coffee, monuments, restaurants, cafes):
     -> ALWAYS set "should_show_cards": true!
     -> ALWAYS include those exact 2-3 mentioned places in "places" so interactive cards appear in the UI with ratings, est. price, and Google Maps links!
     -> Even when answering opening hours (e.g. 'ye oen time bta kal hai date 4pm ko'), ALWAYS include those venues in "places" so the user keeps the cards!
   - ONLY set "should_show_cards": false if the message has NO specific venues/spots mentioned (e.g. pure weather alert, generic packing advice, or basic greeting).

3. HIGH-END DINING, ROMANTIC DATES & ACTIVE CROSS-QUESTIONING (NO GENERIC DUMPS):
   - ABSOLUTE BAN ON GENERIC DUMPS & BUDGET DILUTION:
     * When user asks for a 'high-end restaurant', 'fine dining', 'romantic date', 'luxury dining', 'rooftop date', or 'anniversary dinner':
     * NEVER EVER suggest budget sweet shops / thali joints (Haldiram's, Bikanervala), fast food counters, casual food court joints, or roadside tea stalls (Chaayos, Chai Point)! That is an absolute mood-killer and users hate it.
     * Do NOT dump generic mass-market buffet chains (like Barbeque Nation) as high-end luxury.
   - ACTIVE CROSS-QUESTIONING (Clarify Before Assuming):
     * Do NOT dump 3 random generic chain restaurants when preferences are open!
     * Act like a high-taste, street-smart local concierge:
       1) Acknowledge the date / occasion with style and enthusiasm.
       2) Ask 2 sharp, specific cross-questions to pinpoint the exact vibe:
          - Ambience: Quiet romantic candle-light / 5-star fine dining vs. Energetic rooftop lounge with craft cocktails & live music?
          - Cuisine: Awadhi / Royal Mughlai & Kebabs, Pan-Asian / Sushi, Italian / Gourmet European, or Pure Veg fine-dining?
          - Budget Expectation: Upscale casual (~₹1,500/head) or 5-Star Luxury (~₹2,500 - ₹3,500/head)?
       3) Give 1-2 curated teaser examples for each vibe right in the text:
          - E.g. for Pitampura / North-West Delhi:
            * 5-Star Luxury Candle-Light: 'The Great Kabab Factory' or 'Indyaki' at Radisson Blu Hotel, Pitampura (~₹3,000 for two).
            * Classy Rooftop & Cocktails: 'Dorado' or 'The Flying Dutchman' at Netaji Subhash Place (NSP) (~₹2,000 for two).
            * Or Punjabi Bagh Club Road (7 mins away): 'Town Hall' or 'Ditas' for luxury Pan-Asian/European aesthetic.
          - E.g. for Dwarka: 'Pavilion 75' (Welcomhotel ITC Dwarka) or 'Creo' (Vivanta by Taj Dwarka).
          - E.g. for Central/South Delhi: 'Olive Bar & Kitchen' Mehrauli, 'Indian Accent' Lodhi, or 'Bukhara' ITC Maurya.
       4) Set "places" to the 2-3 genuine upscale venues mentioned so the user gets real high-end cards immediately.
       5) Set "quick_replies" to 3-4 specific vibe chips (e.g. ["Candle-light 5-star", "Rooftop lounge & cocktails", "Pan-Asian / Italian", "Pure veg fine-dining"]) so the user can answer with a single tap!

4. SPECIFIC DISH & CUISINE REALITY (NO DUMB BLURTS):
   - ABSOLUTE BAN ON SAYING 'Swiggy Dineout ke verified partners mein dal makhni / yeh dish nahi hai' or 'yahan yeh khana nahi milta'! That sounds foolish. Indian hubs (Rohini, Pitampura, CP, Rajouri, Karol Bagh, etc.) are food paradises with countless iconic North Indian restaurants, dhabas, and family dining spots!
   - When asked for specific dishes (e.g. 'dal makhni', 'butter chicken', 'chole bhature', 'biryani', 'momos'):
     * NEVER recommend pure dessert/waffle/bakery places (like Choko La, Belgian Waffle)!
     * Always recommend the 2-3 genuine, iconic, highly-rated spots for that exact dish in that locality!
       (e.g., For Dal Makhni in Rohini: 'Moti Mahal Delux' in Sector 10 / Metro Walk, 'Sagar Ratna' in Sector 9 DC Chowk, 'Pind Balluchi' at Metro Walk Sec 10, 'Invitation Restaurant' in Sector 7, 'Sandoz' Sector 9, 'Prem Dhaba').
     * Mention the exact Sector / Market (e.g. Sector 9 DC Chowk, Sector 10 Metro Walk).
     * Set "places" to these exact venues so their interactive cards with Google Maps pins and directions render cleanly!

4. LIVE EVENTS, MOVIES & NIGHTLIFE (Multi-App Discovery):
   - ONLY mention movies, events, venues, dates, showtimes and prices that appear in the live event data supplied to you. NEVER invent titles, theatres, show slots or prices from memory.
   - If the live data has no matching event, say so plainly in one short line and point the user to the booking link; do not fill the gap with guesses.
   - FOR MOVIES & CINEMA: name the movies from the supplied data and describe them only with details present in that data. If venue or showtimes are missing, say they are not listed and link to BookMyShow.
   - FOR LIVE GIGS & COMEDY: recommend the supplied events (e.g. '{top_event.get("title") if top_event else "the top event in the live data"}') using only the fields provided.
   - INLINE STRUCTURE RULE: Describe each movie or event in its own distinct paragraph separated by blank lines! The UI automatically embeds the interactive booking card right after your paragraph explaining that movie or event!
   - Set "action_type": "live_events".
   - Include "ticket_card": {{"title": "{top_event.get('title') if top_event else 'Movie / Live Event'}", "venue": "{top_event.get('venue') if top_event else city}", "date_time": "{top_event.get('date_time', 'Tomorrow') if top_event else 'Tomorrow'}", "price_range": "{top_event.get('price_range_inr', '₹250 - ₹550') if top_event else '₹250 - ₹550'}", "booking_url": "{top_event.get('booking_url', 'https://in.bookmyshow.com') if top_event else 'https://in.bookmyshow.com'}", "provider": "{top_event.get('booking_provider', 'BookMyShow') if top_event else 'BookMyShow'}"}}.
   - Only include separate food/cafe spots in "places" if suggesting pre/post movie/gig snacks (e.g. coffee, burgers, momos).

4. MONUMENT PASS / TICKET:
   - action_type: "instant_pass", provide ticket_card.

Return ONLY a strict JSON object with:
{{
  "reply_text": "Authentic Hinglish response string (Use single quotes inside text like 'kulhad chai'. DO NOT include 'Quick Replies:' or raw JSON in the text)",
  "action_type": "general_chat" | "food_recommendation" | "instant_pass" | "live_events",
  "should_show_cards": true/false,
  "places": [
    {{
      "name": "Exact Name of Store/Venue (e.g. 'Berco\'s', 'Third Wave Coffee', 'Chache Di Hatti')",
      "address": "Full Specific Landmark with Mall/Market name, Locality and City (e.g. 'Pacific Mall, Subhash Nagar, Delhi' or 'Sector 14 Market, Dwarka, Delhi'). NEVER write '...' or truncated addresses!",
      "cuisines": ["Chinese", "Dimsum"],
      "estimated_cost_per_person": 500,
      "rating": 4.5,
      "category": "restaurant" | "cafe" | "street_food",
      "is_bookable": true
    }}
  ],
  "ticket_card": null,
  "quick_replies": ["Suggestion 1", "Suggestion 2", "Suggestion 3"]
}}
"""
        raw_ai = call_ai_engine(
            prompt=ai_prompt,
            system_prompt=LIVE_COPILOT_PROMPT,
            conversation_history=history_turns,
        )

        parsed_data = extract_clean_copilot_payload(raw_ai)
        reply_text = parsed_data.get("reply_text") or (
            f"Bhai {locality} mein ho! Main aapka live copilot hu in {city}. Batao kya plan hai — mast khana, live events, ya koi spot explore karna hai?"
        )

        # Clean trailing raw headers if any
        for marker in ["**Quick Replies:**", "### 💬 Quick Replies", "**Quick Actions:**", "### 📍 Quick Actions"]:
            if marker in reply_text:
                reply_text = reply_text.split(marker)[0].strip()

        action_type_str = parsed_data.get("action_type", "general_chat")
        action_type_map = {
            "food_recommendation": LiveCopilotActionType.FOOD_RECOMMENDATION,
            "live_events": LiveCopilotActionType.LIVE_EVENTS,
            "instant_pass": LiveCopilotActionType.INSTANT_PASS,
            "monument_discovery": LiveCopilotActionType.MONUMENT_DISCOVERY,
            "general_chat": LiveCopilotActionType.GENERAL_CHAT,
        }
        action_type = action_type_map.get(action_type_str, LiveCopilotActionType.GENERAL_CHAT)

        # Step 4: Handle Structured Places Cards with Resilient In-Text Fallback
        recommended_places: List[PlaceItem] = []
        ai_places = parsed_data.get("places", [])

        # If model discussed places in text but didn't put them in places array, auto-extract!
        if not ai_places:
            extracted_names = []
            # Extract bullet items like "- Chaayos:", "- Third Wave Coffee:"
            bullets = re.findall(r'^[ \t]*[-*•]\s*\*{0,2}([A-Za-z0-9\s\',&]+?)\*{0,2}\s*:', reply_text, re.MULTILINE)
            for b in bullets:
                clean_b = b.strip().strip("'\"*")
                if len(clean_b) > 2 and clean_b.lower() not in ["timing", "timings", "note", "tip", "mera plan", "budget", "metro", "open now"]:
                    extracted_names.append(clean_b)

            # Extract bold names like "**Chaayos**" or "**Hungry Eyes**"
            bolds = re.findall(r'\*\*([A-Za-z0-9\s\',&]+?)\*\*', reply_text)
            for b in bolds:
                clean_b = b.strip().strip("'\"*")
                if len(clean_b) > 2 and clean_b not in extracted_names and clean_b.lower() not in ["timing", "timings", "note", "tip", "mera plan", "budget", "metro", "open now"]:
                    extracted_names.append(clean_b)

            if extracted_names:
                for v_name in extracted_names[:3]:
                    cat = "cafe" if any(w in v_name.lower() for w in ["cafe", "coffee", "tea", "chaayos", "third wave", "starbucks"]) else "street_food"
                    ai_places.append({
                        "name": v_name,
                        "address": f"{locality}, {city}",
                        "cuisines": ["Cafe & Snacks"] if cat == "cafe" else ["Street Food", "Momos"],
                        "estimated_cost_per_person": 200 if cat == "cafe" else 100,
                        "rating": 4.6,
                        "category": cat,
                        "is_bookable": False,
                    })

        should_show_cards = parsed_data.get("should_show_cards", False) or bool(ai_places)

        if should_show_cards and ai_places:
            for p in ai_places:
                p_name = p.get("name", "Local Spot")
                p_addr = p.get("address", f"{locality}, {city}")
                p_cuisines = p.get("cuisines", ["Street Food", "Regional"])
                p_cost = float(p.get("estimated_cost_per_person", 100))
                p_rating = float(p.get("rating", 4.6))
                is_bookable = bool(p.get("is_bookable", False))

                cat_str = str(p.get("category", "")).lower()
                is_event_venue = any(w in p_name.lower() or w in cat_str for w in ["stadium", "auditorium", "arena", "ground", "antisocial", "piano man", "concert", "comedy", "theatre"])
                if is_event_venue or "event" in cat_str:
                    p_cat = PlaceCategory.BAR_NIGHTLIFE if any(w in p_name.lower() for w in ["antisocial", "club", "piano man", "bar"]) else PlaceCategory.ACTIVITY
                    is_bookable = False
                elif "cafe" in cat_str:
                    p_cat = PlaceCategory.CAFE
                elif "restaurant" in cat_str and p_cost >= 400:
                    p_cat = PlaceCategory.RESTAURANT
                else:
                    p_cat = PlaceCategory.MARKET
                    is_bookable = False  # Street food, carts and stalls never have table reservations

                # Clean destination query for Google Maps (Ensure exact store + landmark + city)
                clean_name = p_name.strip()
                clean_addr = re.sub(r'[\.]{2,}', '', str(p_addr)).strip().rstrip(',. ')
                if city.lower() not in clean_addr.lower():
                    full_dest = f"{clean_name}, {clean_addr}, {city}"
                else:
                    full_dest = f"{clean_name}, {clean_addr}"

                encoded_dest = urllib.parse.quote(full_dest)
                # Exact Turn-by-Turn Navigation URL from user's current GPS location
                directions_url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_dest}"
                # Exact Store Profile / Review Listing URL
                maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_dest}"

                recommended_places.append(
                    PlaceItem(
                        id=f"spot_{uuid.uuid4().hex[:6]}",
                        name=p_name,
                        category=p_cat,
                        description=f"Local spot in {locality} known for {', '.join(p_cuisines[:2])}.",
                        address=clean_addr if clean_addr else f"{locality}, {city}",
                        location=GeoLocation(lat=lat, lng=lng),
                        cuisines=p_cuisines,
                        price_band=PriceBand.BUDGET if p_cost < 250 else PriceBand.MODERATE,
                        estimated_cost_per_person=p_cost,
                        rating=p_rating,
                        google_maps_url=maps_url,
                        directions_url=directions_url,
                        photo_urls=["https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=800"],
                        source_provider="local_ai",
                        is_bookable=is_bookable,
                    )
                )

        # Step 5: Handle Ticket Booking Cards, Swiggy Food/Dineout Cards, or Live Event Cards
        ticket_card = parsed_data.get("ticket_card")
        ticket_cards: List[Dict[str, Any]] = []

        # If Swiggy Dineout table reservations were found, populate into recommended_places for rich in-app booking cards
        if swiggy_cards and any(c.get("category") == "table_reservation" for c in swiggy_cards):
            for sc in swiggy_cards:
                r_name = sc.get("name") or sc.get("title", "").replace("Dineout: ", "")
                r_addr = sc.get("venue", f"{locality}, {city}")
                if not any(r_name.lower() in p.name.lower() or p.name.lower() in r_name.lower() for p in recommended_places):
                    encoded_dest = urllib.parse.quote(f"{r_name}, {r_addr}")
                    recommended_places.append(
                        PlaceItem(
                            id=sc["id"],
                            name=r_name,
                            category=PlaceCategory.RESTAURANT,
                            description=sc.get("description"),
                            address=r_addr,
                            # Swiggy MCP returns no coordinates; the search point is used as a placeholder.
                            location=GeoLocation(lat=lat, lng=lng),
                            cuisines=sc.get("cuisines") or [],
                            estimated_cost_per_person=sc.get("cost_per_person"),
                            rating=sc.get("rating"),
                            google_maps_url=f"https://www.google.com/maps/search/?api=1&query={encoded_dest}",
                            directions_url=f"https://www.google.com/maps/dir/?api=1&destination={encoded_dest}",
                            source_provider="swiggy_dineout",
                            is_bookable=True,
                        )
                    )

        if swiggy_cards and not any(c.get("category") == "table_reservation" for c in swiggy_cards):
            # Only set event ticket_cards for food delivery / instamart cards
            ticket_cards = swiggy_cards[:SWIGGY_FOOD_CARD_LIMIT]
            ticket_card = ticket_cards[0]
            action_type = LiveCopilotActionType.LIVE_EVENTS
        elif action_type == LiveCopilotActionType.LIVE_EVENTS or is_events_query or (ticket_card and ("venue" in ticket_card or "provider" in ticket_card)):
            # The model's own "ticket_card" is ignored here: it invents events ("Live Music Tonight - Delhi").
            # Cards come only from real events found in the catalog.
            candidates = []

            if events_list:
                for ev in events_list:
                    ev_title = ev.get("title") or ""
                    # Deduplicate by title
                    if any((c.get("title") or "").strip().lower() == ev_title.strip().lower() for c in candidates):
                        continue
                    p_name = ev.get("booking_provider")
                    candidates.append({
                        "id": ev.get("id"),
                        "title": ev_title,
                        "category": ev.get("category") or "event",
                        "venue": ev.get("venue"),
                        "date_time": ev.get("date_time"),
                        "price_range": ev.get("price_range_inr"),
                        "booking_url": self.generate_booking_url(p_name, ev_title, ev.get("booking_url"), city=city),
                        "provider": p_name,
                        "description": ev.get("description"),
                    })

            if candidates:
                ticket_cards = candidates[:EVENT_CARD_LIMIT]
                ticket_card = ticket_cards[0]
            else:
                ticket_card, ticket_cards = None, []
            action_type = LiveCopilotActionType.LIVE_EVENTS

            # Clean duplicate venues from recommended_places if covered by ticket_cards
            if ticket_cards and recommended_places:
                # Empty names are skipped: "" is a substring of every place name and would remove them all.
                v_names = [(c.get("venue") or "").lower() for c in ticket_cards if c.get("venue")]
                t_names = [(c.get("title") or "").lower() for c in ticket_cards if c.get("title")]
                recommended_places = [
                    p for p in recommended_places
                    if not any(
                        (len(p.name) > 3 and (p.name.lower() in v or v in p.name.lower() or p.name.lower() in t or t in p.name.lower()))
                        for v in v_names for t in t_names
                    )
                ]

        elif action_type == LiveCopilotActionType.INSTANT_PASS or (ticket_card and not ("venue" in ticket_card or "provider" in ticket_card)):
            p_name = (ticket_card.get("title") if ticket_card else None) or f"{city} Monument Fast-Track"
            fee = float((ticket_card.get("amount_inr") or ticket_card.get("entry_fee_inr") or 150.0) if ticket_card else 150.0)
            checkout = create_checkout_session_tool(
                amount_inr=fee,
                description=f"Instant Fast-Track Pass: {p_name}",
            )
            ticket_card = {
                "title": f"Fast-Track Entry: {p_name}",
                "monument_name": p_name,
                "amount_inr": fee,
                "entry_fee_inr": fee,
                "order_id": checkout.get("order_id", "order_instant_101"),
                "checkout_url": checkout.get("checkout_url"),
                "status": "Ready to Pay",
            }
            ticket_cards = [ticket_card]

        quick_replies = parsed_data.get("quick_replies") or [
            "Best street food nearby 🥟",
            "Where to go next? 🗺️",
            "Book an auto 🛺",
        ]

        # Real Swiggy restaurants first (they can be booked), then the model's own suggestions.
        # An events answer should not carry restaurants the model made up when nobody asked about food.
        if action_type == LiveCopilotActionType.LIVE_EVENTS and not is_dining_or_food_query:
            recommended_places = [p for p in recommended_places if p.source_provider != "local_ai"]
        recommended_places.sort(key=lambda p: p.source_provider != "swiggy_dineout")
        return LiveCopilotResponse(
            reply_text=reply_text,
            action_type=action_type,
            nearby_recommendations=recommended_places[:MAX_PLACE_CARDS],
            ticket_booking_card=ticket_card,
            ticket_booking_cards=ticket_cards,
            suggested_quick_replies=quick_replies[:4],
        )
