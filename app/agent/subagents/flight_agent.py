"""Flight Specialist Subagent equipped with precision flight tools."""
from typing import Optional, List
from app.schemas.agent import FlightSpecialistTask, FlightSpecialistResult, AgentRole
from app.schemas.flight import FlightOption
from app.tools.flights import search_flights_tool
from app.services.smart_tools.flight_tradeoffs import analyze_flight_tradeoffs
from app.tools.registry import get_tools_for_agent


class FlightSpecialistAgent:
    """Specialist subagent for evaluating airline schedules, fares, baggage rules, and deal tradeoffs."""

    def __init__(self):
        self.role = AgentRole.FLIGHT_SPECIALIST
        self.authorized_tools = get_tools_for_agent(self.role)

    def run(self, task: FlightSpecialistTask) -> FlightSpecialistResult:
        # Tool 1: search_flights
        search_res = search_flights_tool(
            origin=task.origin,
            destination=task.destination,
            departure_date=task.departure_date,
            return_date=task.return_date,
            adult_count=task.passengers,
        )

        raw_flights = search_res.get("flights", [])
        if not raw_flights:
            # No supplier configured: use the Tripora flight catalogue (airlines, times and fares).
            from app.services.mock_bridge import flights as bridge_flights
            raw_flights = bridge_flights(task.origin, task.destination, task.departure_date, task.return_date, task.passengers)
        if not raw_flights:
            return FlightSpecialistResult(
                success=False,
                recommended_flights=[],
                cheapest_fare=0.0,
                notes=["No flights found for the specified route and dates."],
            )

        flight_options = [FlightOption(**f) for f in raw_flights]

        # Filter by budget if specified
        if task.max_flight_budget:
            within_budget = [f for f in flight_options if f.published_fare <= task.max_flight_budget]
            if within_budget:
                flight_options = within_budget

        # Filter by preferred carrier if specified
        if task.preferred_carrier:
            pref = task.preferred_carrier.lower()
            matching = [f for f in flight_options if pref in f.airline_name.lower() or pref in f.airline_code.lower()]
            if matching:
                flight_options = matching

        # Tool 2: analyze_flight_tradeoffs (Deal Hunter & Red-Eye Detector)
        tradeoff_analysis = analyze_flight_tradeoffs(flight_options)

        cheapest_fare = tradeoff_analysis.get("cheapest_flight", {}).get("fare", 0.0)
        fastest_id = tradeoff_analysis.get("fastest_flight", {}).get("id")
        best_val_id = tradeoff_analysis.get("best_value_flight", {}).get("id")

        # Sort with best value flight first, then cheapest
        sorted_recommendations = sorted(
            flight_options,
            key=lambda x: (x.id != best_val_id, x.published_fare),
        )

        notes = [
            f"Evaluated {len(flight_options)} available flights on {task.origin} -> {task.destination}.",
            f"Best overall value: {tradeoff_analysis.get('best_value_flight', {}).get('airline', 'Flight')} (₹{tradeoff_analysis.get('best_value_flight', {}).get('fare', 0):,.0f}).",
            "Standard baggage: 7kg cabin + 15kg check-in included per passenger.",
        ]

        # Inject red-eye alerts if any
        for rw in tradeoff_analysis.get("red_eye_warnings", []):
            notes.append(f"⚠️ {rw['warning']}")

        # Inject time-shift savings if any
        for ts in tradeoff_analysis.get("time_shift_savings", []):
            notes.append(f"💡 {ts['tip']}")

        if any(f.is_lcc for f in sorted_recommendations[:3]):
            notes.append("Low-cost carriers (IndiGo, Akasa) charge separately for hot meals and seat selection.")

        return FlightSpecialistResult(
            success=True,
            recommended_flights=sorted_recommendations[:3],
            cheapest_fare=cheapest_fare,
            fastest_flight_id=fastest_id,
            notes=notes,
        )
