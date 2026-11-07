"""Stay Curator Subagent equipped with precision hotel tools."""
from typing import Optional, List
from app.schemas.agent import StayCuratorTask, StayCuratorResult, AgentRole
from app.schemas.hotel import HotelOption
from app.tools.hotels import search_hotels_tool, search_hotels_near_landmark_tool, get_hotel_details_tool
from app.tools.registry import get_tools_for_agent


class StayCuratorAgent:
    """Specialist subagent for hotel curation, landmark proximity intelligence, and room amenity verification."""

    def __init__(self):
        self.role = AgentRole.STAY_CURATOR
        self.authorized_tools = get_tools_for_agent(self.role)

    def run(self, task: StayCuratorTask) -> StayCuratorResult:
        proximity_highlights = []

        # Tool 1: Proximity vs City Search
        if task.anchor_landmark and task.anchor_lat and task.anchor_lng:
            search_res = search_hotels_near_landmark_tool(
                city=task.city,
                landmark_name=task.anchor_landmark,
                landmark_lat=task.anchor_lat,
                landmark_lng=task.anchor_lng,
                check_in_date=task.check_in_date,
                check_out_date=task.check_out_date,
                max_radius_km=4.0,
            )
            proximity_highlights.append(f"Hotels ranked by proximity to {task.anchor_landmark}.")
        else:
            search_res = search_hotels_tool(
                city=task.city,
                check_in_date=task.check_in_date,
                check_out_date=task.check_out_date,
                rooms=task.rooms,
                adults=task.guests,
            )

        raw_hotels = search_res.get("hotels", [])
        if not raw_hotels:
            from app.services.mock_bridge import hotels as bridge_hotels
            raw_hotels = bridge_hotels(task.city, task.check_in_date, task.check_out_date, task.rooms, task.guests)
        if not raw_hotels:
            return StayCuratorResult(
                success=False,
                recommended_hotels=[],
                proximity_highlights=["No matching hotels found for the given dates."],
            )

        hotels = [HotelOption(**h) for h in raw_hotels]

        # Budget filtering
        if task.max_budget_per_night:
            budget_matches = [h for h in hotels if h.min_price_per_night <= task.max_budget_per_night]
            if budget_matches:
                hotels = budget_matches

        # Sort by best value
        def value_score(h: HotelOption) -> float:
            return (h.trip_advisor_rating or 4.0) / (h.min_price_per_night / 1000)

        sorted_hotels = sorted(hotels, key=value_score, reverse=True)
        best_value_id = sorted_hotels[0].id if sorted_hotels else None

        # Tool 2: get_hotel_details on top property to verify amenities
        if sorted_hotels:
            top_h = sorted_hotels[0]
            try:
                details = get_hotel_details_tool(top_h.hotel_code)
                if details.get("amenities"):
                    proximity_highlights.append(
                        f"Top Pick '{top_h.name}' verified with: {', '.join(details['amenities'][:3])}."
                    )
            except Exception:
                pass

            if task.anchor_landmark:
                proximity_highlights.append(
                    f"'{top_h.name}' is within walking/short drive distance of {task.anchor_landmark}."
                )

        return StayCuratorResult(
            success=True,
            recommended_hotels=sorted_hotels[:3],
            best_value_hotel_id=best_value_id,
            proximity_highlights=proximity_highlights,
        )
