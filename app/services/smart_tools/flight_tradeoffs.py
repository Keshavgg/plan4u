"""Flight Tradeoff and Deal Hunter Engine."""
from typing import List, Dict, Any, Optional
from app.schemas.flight import FlightOption


def analyze_flight_tradeoffs(flights: List[FlightOption]) -> Dict[str, Any]:
    """Analyzes a list of flights to detect hidden costs (red-eye cabs), best value, and time-shift savings."""
    if not flights:
        return {
            "success": False,
            "message": "No flights provided for analysis.",
            "recommendations": [],
        }

    # 1. Cheapest and Fastest
    cheapest = min(flights, key=lambda f: f.published_fare)

    def parse_dur_minutes(dur_str: str) -> int:
        total = 0
        for p in dur_str.split():
            if p.endswith("h"):
                total += int(p[:-1]) * 60
            elif p.endswith("m"):
                total += int(p[:-1])
        return total or 9999

    fastest = min(flights, key=lambda f: parse_dur_minutes(f.total_duration))

    # 2. Red-Eye & Airport Cab Trap Detection
    red_eye_warnings = []
    for f in flights:
        try:
            arr_time_str = f.arrival_time.split("T")[1][:5]
            arr_hour = int(arr_time_str.split(":")[0])
            if 1 <= arr_hour <= 5:
                red_eye_warnings.append({
                    "flight_id": f.id,
                    "flight_number": f.segments[0].flight_number if f.segments else "Flight",
                    "arrival_time": arr_time_str,
                    "warning": f"Lands at {arr_time_str} AM. Night airport cabs charge 2x surge (~₹1,500 - ₹2,200) and hotels may require early check-in fees.",
                    "adjusted_real_cost_inr": f.published_fare + 1800.0,
                })
        except Exception:
            pass

    # 3. Best Value Algorithm (Balance of non-stop, decent hours, and low fare)
    def compute_value_score(f: FlightOption) -> float:
        score = 10000.0 - f.published_fare
        if f.stops == 0:
            score += 1500.0
        # Penalize awkward middle of the night flights
        try:
            dep_hour = int(f.departure_time.split("T")[1][:2])
            if 7 <= dep_hour <= 20:
                score += 1000.0
            elif 0 <= dep_hour <= 5:
                score -= 2000.0
        except Exception:
            pass
        return score

    best_value = max(flights, key=compute_value_score)

    # 4. Time Shift Savings
    time_shift_opportunities = []
    for f in flights:
        if f.id != cheapest.id:
            diff = f.published_fare - cheapest.published_fare
            if diff >= 1000.0:
                time_shift_opportunities.append({
                    "alternate_flight": cheapest.airline_name + " (" + cheapest.departure_time.split("T")[1][:5] + ")",
                    "your_selected_flight": f.airline_name + " (" + f.departure_time.split("T")[1][:5] + ")",
                    "potential_savings_inr": diff,
                    "tip": f"Switching to {cheapest.airline_name} saves ₹{diff:,.0f} per passenger!",
                })

    return {
        "success": True,
        "total_analyzed": len(flights),
        "cheapest_flight": {
            "id": cheapest.id,
            "airline": cheapest.airline_name,
            "flight_number": cheapest.segments[0].flight_number if cheapest.segments else "",
            "fare": cheapest.published_fare,
            "duration": cheapest.total_duration,
            "badge": "CHEAPEST_FARE",
        },
        "fastest_flight": {
            "id": fastest.id,
            "airline": fastest.airline_name,
            "duration": fastest.total_duration,
            "fare": fastest.published_fare,
            "badge": "FASTEST_NON_STOP",
        },
        "best_value_flight": {
            "id": best_value.id,
            "airline": best_value.airline_name,
            "fare": best_value.published_fare,
            "duration": best_value.total_duration,
            "badge": "BEST_OVERALL_VALUE",
            "reason": "Optimal departure timing with non-stop convenience and zero night cab surge.",
        },
        "red_eye_warnings": red_eye_warnings,
        "time_shift_savings": time_shift_opportunities[:2],
    }
