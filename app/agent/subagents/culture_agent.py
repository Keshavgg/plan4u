"""Culture & Food Guide Subagent equipped with precision cultural, dining, and clustering tools."""
from typing import List, Optional
from app.schemas.agent import CultureFoodTask, CultureFoodResult, AgentRole
from app.schemas.attraction import PlaceItem, PlaceCategory
from app.schemas.itinerary import DayPlan, ScheduledActivity, TimeSlot, TravelPace
from app.tools.attractions import search_attractions_tool
from app.tools.dining import search_restaurants_tool, search_cafes_tool
from app.services.smart_tools.weather_service import get_destination_weather_insights
from app.services.smart_tools.spatial_clustering import cluster_places_by_geography
from app.services.smart_tools.transport_estimator import estimate_transport_options
from app.tools.registry import get_tools_for_agent


class CultureFoodAgent:
    """Specialist subagent for heritage monuments, cultural storytelling, zero-backtrack clustering, and dining pairing."""

    def __init__(self):
        self.role = AgentRole.CULTURE_FOOD_GUIDE
        self.authorized_tools = get_tools_for_agent(self.role)

    def run(self, task: CultureFoodTask) -> CultureFoodResult:
        # Tool 1: get_destination_weather_insights (Golden-Hour & Climate Guide)
        weather_info = get_destination_weather_insights(city=task.destination)
        w_data = weather_info.get("weather", {})
        sunset_time = w_data.get("sunset")
        golden_hour_evening = w_data.get("golden_hours", {}).get("evening")

        # Tool 2: search_attractions
        attractions_res = search_attractions_tool(city=task.destination)
        raw_places = attractions_res.get("places", [])
        monuments = [PlaceItem(**p) for p in raw_places]

        # Tool 3: search_restaurants & search_cafes
        rest_res = search_restaurants_tool(city_or_area=task.destination, cuisine=task.dietary_preferences)
        restaurants = [PlaceItem(**r) for r in rest_res.get("restaurants", [])]

        cafe_res = search_cafes_tool(city_or_area=task.destination)
        cafes = [PlaceItem(**c) for c in cafe_res.get("cafes", [])]

        all_dining = restaurants + cafes

        # Tool 4: cluster_places_by_geography (Zero-Backtrack Smart Clustering)
        items_to_cluster = []
        for m in monuments[:6]:
            items_to_cluster.append({
                "type": "monument",
                "item": m,
                "name": m.name,
                "lat": m.location.lat,
                "lng": m.location.lng,
            })
        for r in restaurants[:4]:
            items_to_cluster.append({
                "type": "restaurant",
                "item": r,
                "name": r.name,
                "lat": r.location.lat,
                "lng": r.location.lng,
            })

        cluster_res = cluster_places_by_geography(items_to_cluster, days_count=task.duration_days)
        clusters = cluster_res.get("clusters", [])

        # Build day plans from clustered sectors
        day_plans: List[DayPlan] = []
        for day_idx in range(task.duration_days):
            day_num = day_idx + 1
            activities: List[ScheduledActivity] = []
            day_cost = 0.0

            # Pull places from cluster if available
            clustered_items = clusters[day_idx]["places"] if day_idx < len(clusters) else []
            cluster_monuments = [p["item"] for p in clustered_items if p["type"] == "monument"]
            cluster_dining = [p["item"] for p in clustered_items if p["type"] == "restaurant"]

            # Fallbacks if cluster is sparse
            if not cluster_monuments and day_idx < len(monuments):
                cluster_monuments = [monuments[day_idx]]
            if not cluster_dining and day_idx < len(restaurants):
                cluster_dining = [restaurants[day_idx]]

            # 1. Morning Activity (Monument)
            if cluster_monuments:
                m = cluster_monuments[0]
                fee = m.entry_fee or 100.0
                day_cost += fee
                activities.append(
                    ScheduledActivity(
                        time_slot=TimeSlot.MORNING,
                        start_time="09:00 AM",
                        end_time="11:30 AM",
                        title=f"Explore {m.name}",
                        category=m.category,
                        description=m.description or f"Guided exploration of {m.name}.",
                        place=m,
                        estimated_cost_inr=fee,
                        travel_time_from_prev="15 mins by cab",
                        insider_tips=[m.best_time_slot or "Visit early to avoid crowds."],
                    )
                )

            # 2. Lunch Stop (Adjacent Dining)
            if cluster_dining:
                rest = cluster_dining[0]
                food_cost = rest.estimated_cost_per_person or 500.0
                day_cost += food_cost
                activities.append(
                    ScheduledActivity(
                        time_slot=TimeSlot.AFTERNOON,
                        start_time="01:00 PM",
                        end_time="02:30 PM",
                        title=f"Traditional Lunch at {rest.name}",
                        category=PlaceCategory.RESTAURANT,
                        description=f"Authentic local lunch featuring {', '.join(rest.cuisines) if rest.cuisines else 'regional delicacies'}.",
                        place=rest,
                        estimated_cost_inr=food_cost,
                        travel_time_from_prev="5 mins walk (same cluster)",
                        insider_tips=["Try their chef's special signature thali/platter."],
                    )
                )

            # 3. Sunset / Golden Hour (Monument or Viewpoint)
            if len(cluster_monuments) > 1 or (day_idx + 1 < len(monuments)):
                m2 = cluster_monuments[1] if len(cluster_monuments) > 1 else monuments[(day_idx + 1) % len(monuments)]
                fee2 = m2.entry_fee or 50.0
                day_cost += fee2
                activities.append(
                    ScheduledActivity(
                        time_slot=TimeSlot.EVENING,
                        start_time="04:30 PM",
                        end_time="06:30 PM",
                        title=f"Sunset & Golden Hour at {m2.name}",
                        category=m2.category,
                        description=(
                            f"Witness the sunset (Golden hour: {golden_hour_evening})."
                            if golden_hour_evening else "Witness the sunset."
                        ),
                        place=m2,
                        estimated_cost_inr=fee2,
                        travel_time_from_prev="10 mins by auto-rickshaw",
                        insider_tips=[f"Sunset occurs at ~{sunset_time}. Best panoramic photos guaranteed."],
                    )
                )

            # 4. Night / Rooftop Cafe
            if cafes:
                c = cafes[day_idx % len(cafes)]
                c_cost = c.estimated_cost_per_person or 350.0
                day_cost += c_cost
                activities.append(
                    ScheduledActivity(
                        time_slot=TimeSlot.NIGHT,
                        start_time="08:00 PM",
                        end_time="10:00 PM",
                        title=f"Evening Chill at {c.name}",
                        category=PlaceCategory.CAFE,
                        description=f"Unwind with artisan beverages and snacks at {c.name}.",
                        place=c,
                        estimated_cost_inr=c_cost,
                        travel_time_from_prev="10 mins drive",
                        insider_tips=["Great cozy ambiance, live music, and specialty brews."],
                    )
                )

            day_plans.append(
                DayPlan(
                    day_number=day_num,
                    date=f"Day {day_num}",
                    theme=f"{task.destination.title()} Sector {day_num} — Heritage & Culinary Walk",
                    activities=activities,
                    daily_budget_estimate=day_cost,
                )
            )

        tips = [f"Optimized with Zero-Backtrack spatial clustering: {cluster_res.get('optimization_summary', '')}"]
        if sunset_time:
            tips.append(f"Golden hour timing: Sunset is at {sunset_time}. Ideal for panoramic sunset viewpoints.")

        return CultureFoodResult(
            success=True,
            top_monuments=monuments[:5],
            recommended_dining=all_dining[:6],
            day_plans=day_plans,
            local_secrets_and_tips=tips,
        )
