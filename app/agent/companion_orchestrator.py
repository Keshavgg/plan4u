"""Live In-Trip Companion Orchestrator (Panel 2)."""
from typing import Dict, Optional
import datetime
import json
from app.config import settings
from app.schemas.agent import LiveCopilotQuery, LiveCopilotResponse
from app.schemas.attraction import GeoLocation
from app.agent.state import CompanionState, ChatMessage
from app.agent import chat_booking, message_analysis
from app.agent.subagents.copilot_agent import LiveCopilotAgent, quick_llm


class CompanionOrchestrator:
    """Manages active traveler sessions and real-time on-trip interactions."""

    def __init__(self):
        self.copilot_agent = LiveCopilotAgent()
        self._sessions: Dict[str, CompanionState] = {}

    def get_or_create_session(self, session_id: str, city: str = "Delhi") -> CompanionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = CompanionState(
                session_id=session_id,
                active_city=city,
            )
        return self._sessions[session_id]

    def reset_session(self, session_id: str):
        """Completely flush conversation memory and recommendations for the given session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def handle_message(self, session_id: str, query: LiveCopilotQuery, user_id: Optional[str] = None) -> LiveCopilotResponse:
        session = self.get_or_create_session(session_id)
        session.current_location = GeoLocation(lat=query.current_lat, lng=query.current_lng)

        # 1. Sync conversation history from session if client didn't supply full history
        if not query.conversation_history and session.chat_history:
            query.conversation_history = session.chat_history[-8:]

        # 2. One AI call reads the message for everything at once: stated preferences, a table-booking request,
        #    and what the user wants to find. (These used to be three sequential calls.)
        analysis = message_analysis.analyze(query, session, user_id)

        # 2b. Upsert stated preferences into Dual-Layer User Memory (VDC Pattern)
        user_memory = None
        def _llm_yes_no(prompt: str) -> bool:
            """Ask the LLM a yes/no question. Returns False on any error."""
            try:
                return (quick_llm(prompt) or "").strip().lower().startswith("yes")
            except Exception:
                return False

        try:
            from app.services.database_service import db_service
            extracted = analysis["memory"]

            if extracted.get("diet"):
                db_service.upsert_user_memory(session_id, "fact", "diet", extracted["diet"], confidence=1.0)
            if extracted.get("budget_tier"):
                db_service.upsert_user_memory(session_id, "fact", "budget_tier", extracted["budget_tier"], confidence=1.0)
            if extracted.get("vibe"):
                db_service.upsert_user_memory(session_id, "recollection", "vibe", extracted["vibe"], confidence=0.95)

            user_memory = db_service.get_user_memory(session_id)
        except Exception as ex:
            print(f"[CompanionOrchestrator] Memory sync warning: {ex}")

        # 3. Record incoming user message
        now_str = datetime.datetime.now().strftime("%I:%M %p")
        session.chat_history.append(
            ChatMessage(role="user", content=query.user_message, timestamp=now_str)
        )

        # 3.5 Table booking from chat: the request is prepared and a confirm card is returned. The model never
        #     confirms anything; only the user pressing the button does.
        booking_response = chat_booking.try_handle(query, session, user_id, analysis["booking"])
        if booking_response is not None:
            session.chat_history.append(
                ChatMessage(role="assistant", content=booking_response.reply_text, timestamp=now_str,
                            metadata={"action_type": "booking"})
            )
            return booking_response

        # 4. Run Live Copilot Agent with Memory
        response = self.copilot_agent.run(query, user_memory=user_memory, user_id=user_id,
                                          precomputed_intent=analysis["intent"])

        # 4. Continuous card persistence: if model returned no cards, but session had cards and topic continues
        # LLM determines whether this is a follow-up on the same topic — zero hardcoded token lists
        combined = query.user_message + " " + response.reply_text

        if not response.nearby_recommendations and session.last_recommended_places:
            try:
                followup_prompt = (
                    "Is this user message a follow-up question about previously shown restaurant/place recommendations "
                    "(e.g. asking about timings, menu, directions, cost, alternatives)? "
                    "Reply with ONLY 'yes' or 'no'.\n"
                    f"User message: \"{query.user_message}\""
                )
                if _llm_yes_no(followup_prompt):
                    response.nearby_recommendations = session.last_recommended_places
            except Exception:
                pass  # conservative: don't persist cards if unsure

        if response.nearby_recommendations:
            session.last_recommended_places = response.nearby_recommendations

        if not response.ticket_booking_cards and session.last_ticket_cards:
            try:
                event_followup_prompt = (
                    "Is this user message a follow-up question about previously shown event/concert/movie ticket bookings "
                    "(e.g. asking about price, timing, how to book, artist, show details)? "
                    "Reply with ONLY 'yes' or 'no'.\n"
                    f"User message: \"{query.user_message}\""
                )
                if _llm_yes_no(event_followup_prompt):
                    response.ticket_booking_cards = session.last_ticket_cards
                    if not response.ticket_booking_card and session.last_ticket_cards:
                        response.ticket_booking_card = session.last_ticket_cards[0]
            except Exception:
                pass

        if response.ticket_booking_cards:
            session.last_ticket_cards = response.ticket_booking_cards

        # 5. Record assistant response
        session.chat_history.append(
            ChatMessage(
                role="assistant",
                content=response.reply_text,
                timestamp=now_str,
                metadata={"action_type": response.action_type},
            )
        )

        return response
