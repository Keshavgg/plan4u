"""Master Pre-Trip Planner Orchestrator (Panel 1)."""
import uuid
import datetime
from app.schemas.itinerary import ItineraryRequest, CompleteItinerary
from app.schemas.agent import (
    FlightSpecialistTask,
    StayCuratorTask,
    CultureFoodTask,
    BudgetCheckoutTask,
)
from app.agent.state import PlannerState
from app.agent.subagents.flight_agent import FlightSpecialistAgent
from app.agent.subagents.stay_agent import StayCuratorAgent
from app.agent.subagents.culture_agent import CultureFoodAgent
from app.agent.subagents.budget_agent import BudgetCheckoutAgent


class PlannerOrchestrator:
    """Orchestrates the 4 pre-trip planning subagents into a unified, bookable itinerary."""

    def __init__(self):
        self.flight_agent = FlightSpecialistAgent()
        self.stay_agent = StayCuratorAgent()
        self.culture_agent = CultureFoodAgent()
        self.budget_agent = BudgetCheckoutAgent()

    def generate_plan(self, request: ItineraryRequest) -> PlannerState:
        state = PlannerState(request=request)
        state.execution_logs.append(f"Starting itinerary generation for {request.destination} ({request.start_date} to {request.end_date})")

        # 1. Calculate duration days
        try:
            d_start = datetime.datetime.strptime(request.start_date, "%Y-%m-%d")
            d_end = datetime.datetime.strptime(request.end_date, "%Y-%m-%d")
            duration_days = max(1, (d_end - d_start).days)
        except Exception:
            duration_days = 3

        # 2. Run Flight Specialist
        state.execution_logs.append(f"Delegating to FlightSpecialist: {request.origin} -> {request.destination}")
        flight_task = FlightSpecialistTask(
            origin=request.origin,
            destination=request.destination,
            departure_date=request.start_date,
            return_date=request.end_date,
            passengers=request.traveler_count,
            max_flight_budget=(request.total_budget * 0.4) if request.total_budget else None,
        )
        state.flight_result = self.flight_agent.run(flight_task)
        state.execution_logs.append(f"FlightSpecialist found {len(state.flight_result.recommended_flights)} flights.")

        # 3. Run Stay Curator
        state.execution_logs.append(f"Delegating to StayCurator for {request.destination}")
        stay_task = StayCuratorTask(
            city=request.destination,
            check_in_date=request.start_date,
            check_out_date=request.end_date,
            rooms=max(1, request.traveler_count // 2),
            guests=request.traveler_count,
            max_budget_per_night=(request.total_budget * 0.3 / duration_days) if request.total_budget else None,
        )
        state.stay_result = self.stay_agent.run(stay_task)
        state.execution_logs.append(f"StayCurator found {len(state.stay_result.recommended_hotels)} hotels.")

        # 4. Run Culture & Food Guide
        state.execution_logs.append(f"Delegating to CultureFoodGuide for {duration_days} days in {request.destination}")
        culture_task = CultureFoodTask(
            destination=request.destination,
            duration_days=duration_days,
            interests=request.interests,
            dietary_preferences=request.dietary_preferences,
            pace=request.pace,
        )
        state.culture_result = self.culture_agent.run(culture_task)
        state.execution_logs.append(f"CultureFoodGuide generated {len(state.culture_result.day_plans)} structured day plans.")

        # 5. Run Budget & Checkout Master
        selected_flight = state.flight_result.recommended_flights[0] if state.flight_result.recommended_flights else None
        selected_hotel = state.stay_result.recommended_hotels[0] if state.stay_result.recommended_hotels else None
        total_activities_cost = sum(dp.daily_budget_estimate for dp in state.culture_result.day_plans)

        state.execution_logs.append("Delegating to BudgetCheckoutMaster for financial reconciliation")
        budget_task = BudgetCheckoutTask(
            total_budget_limit=request.total_budget,
            selected_flight=selected_flight,
            selected_hotel=selected_hotel,
            activities_cost=total_activities_cost,
            days_count=duration_days,
        )
        state.budget_result = self.budget_agent.run(budget_task)

        # 6. Assemble CompleteItinerary with unified intelligence
        itinerary_id = f"itin_{uuid.uuid4().hex[:10]}"
        title = f"Exclusive {duration_days}-Day {request.destination.title()} Getaway"

        all_tips = []
        if state.flight_result and state.flight_result.notes:
            all_tips.extend([f"✈️ {n}" for n in state.flight_result.notes if "saves" in n.lower() or "baggage" in n.lower() or "red-eye" in n.lower()])
        if state.stay_result and state.stay_result.proximity_highlights:
            all_tips.extend([f"🏨 {h}" for h in state.stay_result.proximity_highlights[:2]])
        if state.culture_result and state.culture_result.local_secrets_and_tips:
            all_tips.extend([f"📍 {t}" for t in state.culture_result.local_secrets_and_tips])
        if state.budget_result and state.budget_result.financial_notes:
            all_tips.extend([f"💰 {fn}" for fn in state.budget_result.financial_notes])

        complete_itinerary = CompleteItinerary(
            id=itinerary_id,
            title=title,
            destination=request.destination.title(),
            origin=request.origin.upper(),
            start_date=request.start_date,
            end_date=request.end_date,
            duration_days=duration_days,
            recommended_flights=state.flight_result.recommended_flights,
            selected_flight=selected_flight,
            recommended_hotels=state.stay_result.recommended_hotels,
            selected_hotel=selected_hotel,
            days=state.culture_result.day_plans,
            flight_total_cost=state.budget_result.flight_total,
            hotel_total_cost=state.budget_result.hotel_total,
            dining_and_tickets_cost=state.budget_result.activities_total,
            grand_total_inr=state.budget_result.grand_total,
            best_time_to_visit_note="Ideal weather with pleasant temperatures. Optimal golden-hour lighting for photography.",
            weather_note="Comfortable daytime with cool evenings. Carry a light jacket for late-night heritage strolls.",
            pro_travel_tips=all_tips if all_tips else state.culture_result.local_secrets_and_tips,
            ready_for_checkout=True,
        )

        state.final_itinerary = complete_itinerary
        state.status = "completed"
        state.execution_logs.append("Itinerary compilation completed successfully.")
        return state
