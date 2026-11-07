"""Comprehensive Integration and Regression Test Suite for Plan4U AI Backend."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_panel_1_master_planner():
    r = client.post("/api/v1/planner/generate", json={
        "origin": "DEL",
        "destination": "Jaipur",
        "start_date": "2026-11-15",
        "end_date": "2026-11-17",
        "total_budget": 35000,
        "traveler_count": 2,
        "interests": ["heritage", "cafes"]
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert "itinerary" in data
    assert len(data["itinerary"]["days"]) == 2
    assert data["itinerary"]["grand_total_inr"] > 0


def test_panel_2_live_companion():
    r = client.post("/api/v1/companion/chat", json={
        "user_message": "Bhai Hawa Mahal ke paas mast lassi ya kachori khilao",
        "current_lat": 26.9239,
        "current_lng": 75.8267,
        "current_time_str": "04:30 PM"
    })
    assert r.status_code == 200
    data = r.json()
    assert "reply_text" in data
    assert len(data["reply_text"]) > 10


def test_auto_fetch_nearby_explorer():
    r = client.get("/api/v1/explore/nearby?lat=26.9239&lng=75.8267&radius_km=3.0&city=Jaipur")
    assert r.status_code == 200
    data = r.json()
    assert "hotels" in data
    assert "restaurants" in data
    assert "attractions" in data
    assert "live_events" in data


def test_flights_manual_search():
    r = client.post("/api/v1/flights/search", json={
        "origin": "DEL",
        "destination": "JAI",
        "departure_date": "2026-11-15"
    })
    assert r.status_code == 200
    assert len(r.json()["options"]) > 0


def test_hotels_nearby_gps():
    r = client.get("/api/v1/hotels/nearby?lat=26.9239&lng=75.8267&city=Jaipur")
    assert r.status_code == 200
    assert len(r.json()["options"]) > 0


def test_dining_nearby_gps():
    r = client.get("/api/v1/places/restaurants/nearby?lat=26.9239&lng=75.8267")
    assert r.status_code == 200
    assert len(r.json()["places"]) > 0


def test_events_nearby_gps():
    r = client.get("/api/v1/events/nearby?lat=26.9239&lng=75.8267&city=Jaipur")
    assert r.status_code == 200
    assert len(r.json()["events"]) > 0


def test_smart_tool_reroute():
    r = client.post("/api/v1/tools/companion/reroute", json={
        "current_lat": 26.9239,
        "current_lng": 75.8267,
        "reason": "heavy_rain"
    })
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert len(r.json()["top_alternatives"]) > 0


def test_smart_tool_transport_estimate():
    r = client.post("/api/v1/tools/transport/estimate", json={
        "origin_lat": 26.9239,
        "origin_lng": 75.8267,
        "dest_lat": 26.9855,
        "dest_lng": 75.8513,
        "city": "Jaipur"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["road_distance_km"] > 0
    assert len(data["modes"]) >= 2


def test_smart_tool_group_payment_links():
    r = client.post("/api/v1/tools/group-split/payment-links", json={
        "expenses": [
            {"title": "Dinner at Chokhi Dhani", "amount": 3000, "paid_by": "Amit", "split_among": ["Amit", "Rahul", "Priya"]}
        ],
        "upi_vpa": "amit@okhdfcbank"
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["actionable_settlements"]) == 2
    assert "upi_deep_link" in data["actionable_settlements"][0]


def test_smart_tool_packing_checklist():
    r = client.post("/api/v1/tools/packing/checklist", json={
        "destination": "Jaipur",
        "duration_days": 3,
        "season_or_month": "November",
        "activities": ["sightseeing", "fine dining"]
    })
    assert r.status_code == 200
    assert r.json()["total_items_suggested"] > 10


def test_smart_tool_currency_convert():
    r = client.get("/api/v1/tools/currency/convert?amount=100&from_curr=USD&to_curr=INR")
    assert r.status_code == 200
    assert r.json()["converted_amount"] > 8000


def test_database_cache_service():
    """Verify that caching operations execute on SQL Database without flat JSON files."""
    r = client.get("/api/v1/companion/cache-stats")
    assert r.status_code == 200
    data = r.json()
    assert "database_engine" in data
    assert "total_cache_keys" in data
    assert "total_stored_events" in data
    assert data["total_cache_keys"] > 0


def test_reverse_geocode_service():
    """Verify that real-time GPS coordinates resolve to authentic Indian localities."""
    r = client.get("/api/v1/companion/reverse-geocode?lat=28.7033&lng=77.1325")
    assert r.status_code == 200
    data = r.json()
    assert data["city"] == "Delhi"
    assert "Pitampura" in data["locality"]
    assert "Pitampura" in data["display_name"]


def test_swiggy_mcp_integration():
    """Verify Swiggy MCP protocol discovery, status, food and dineout search endpoints."""
    # 1. Status & discovery
    r = client.get("/api/v1/swiggy/status")
    assert r.status_code == 200
    st = r.json()
    assert "mcp_servers" in st
    assert st["mcp_servers"]["food"] == "https://mcp.swiggy.com/food"
    assert st["mcp_servers"]["dineout"] == "https://mcp.swiggy.com/dineout"
    assert "auth_url" in st

    # 2. Swiggy Food Delivery Search
    rf = client.get("/api/v1/swiggy/food/search?query=Biryani&locality=Dwarka&city=Delhi")
    assert rf.status_code == 200
    food_data = rf.json()
    assert food_data.get("count", 0) > 0
    assert any("Biryani" in p.get("name", "") for p in food_data.get("results", []))
    for p in food_data.get("results", []):
        assert "order_url" in p
        assert p["order_url"].startswith("https://www.swiggy.com")

    # 3. Swiggy Dineout Table Reservation Search (Direct Dynamic URL verification)
    rd = client.get("/api/v1/swiggy/dineout/search?query=Fine+Dining&locality=Connaught+Place&city=Delhi")
    assert rd.status_code == 200
    dineout_data = rd.json()
    assert dineout_data.get("count", 0) > 0
    for d in dineout_data.get("results", []):
        assert "booking_url" in d
        assert "discount_text" in d
        assert "swiggy.com" in d["booking_url"]
        assert "-restaurants" not in d["booking_url"]
        assert "google.com/search" not in d["booking_url"]


def test_copilot_dineout_direct_url_generation():
    """Verify LiveCopilotAgent generates direct Swiggy Dineout search URLs without 404 -restaurants routes."""
    from app.agent.subagents.copilot_agent import LiveCopilotAgent
    
    url = LiveCopilotAgent.generate_booking_url("Swiggy Dineout", "Gulati Restaurant Pandara Road", city="Delhi")
    assert "swiggy.com" in url
    assert "-restaurants" not in url
    assert "google.com/search" not in url

    url_moti = LiveCopilotAgent.generate_booking_url("Dineout", "Moti Mahal Delux", city="Delhi")
    assert "swiggy.com" in url_moti
    assert "-restaurants" not in url_moti

    url_jaipur = LiveCopilotAgent.generate_booking_url("Dineout", "Barbeque Nation", city="Jaipur")
    assert "swiggy.com" in url_jaipur
    assert "-restaurants" not in url_jaipur
    assert "google.com/search" not in url_jaipur


def test_trip_share_and_fork_system():
    """Verify viral trip sharing and 1-click forking mechanism (from VDC architecture)."""
    # 1. Share a trip
    sample_trip = {
        "title": "Weekend Delhi Food & Heritage",
        "destination": "Delhi",
        "origin": "Jaipur",
        "days": 2,
        "budget_inr": 12000,
        "itinerary_data": {
            "title": "Weekend Delhi Food & Heritage",
            "destination": "Delhi",
            "days": [
                {"day_number": 1, "theme": "Old Delhi Street Food & Monuments"},
                {"day_number": 2, "theme": "South Delhi Luxury Cafes"}
            ],
            "grand_total_inr": 12000
        },
        "creator_name": "FoodieExplorer"
    }
    r = client.post("/api/v1/trips/share", json=sample_trip)
    assert r.status_code == 200
    share_res = r.json()
    assert "share_code" in share_res
    assert share_res["share_code"].startswith("TRIP-")
    assert "share_url" in share_res
    code = share_res["share_code"]

    # 2. Retrieve shared trip
    r_get = client.get(f"/api/v1/trips/share/{code}")
    assert r_get.status_code == 200
    trip_data = r_get.json()
    assert trip_data["title"] == sample_trip["title"]
    assert trip_data["creator_name"] == "FoodieExplorer"
    assert "itinerary_data" in trip_data

    # 3. Fork shared trip
    r_fork = client.post(f"/api/v1/trips/share/{code}/fork")
    assert r_fork.status_code == 200
    fork_data = r_fork.json()
    assert fork_data["fork_count"] >= 1
    assert "itinerary" in fork_data
    assert fork_data["itinerary"]["title"] == sample_trip["title"]


def test_dual_layer_user_memory():
    """Verify dual-layer user memory (Facts vs Recollections) persistence and retrieval."""
    user_id = "test_traveler_99"
    
    # 1. Store strict fact
    r1 = client.post(f"/api/v1/user/memory/fact?user_id={user_id}", json={"topic": "diet", "content": "pure_vegetarian"})
    assert r1.status_code == 200
    
    # 2. Store budget tier fact
    r2 = client.post(f"/api/v1/user/memory/fact?user_id={user_id}", json={"topic": "budget_tier", "content": "luxury_fine_dining"})
    assert r2.status_code == 200

    # 3. Retrieve user memory
    r_mem = client.get(f"/api/v1/user/memory?user_id={user_id}")
    assert r_mem.status_code == 200
    mem = r_mem.json()
    assert "facts" in mem
    assert mem["facts"].get("diet") == "pure_vegetarian"
    assert mem["facts"].get("budget_tier") == "luxury_fine_dining"


if __name__ == "__main__":
    print("Running all test functions...")
    test_health_check()
    test_panel_1_master_planner()
    test_panel_2_live_companion()
    test_auto_fetch_nearby_explorer()
    test_flights_manual_search()
    test_hotels_nearby_gps()
    test_dining_nearby_gps()
    test_events_nearby_gps()
    test_smart_tool_reroute()
    test_smart_tool_transport_estimate()
    test_smart_tool_group_payment_links()
    test_smart_tool_packing_checklist()
    test_smart_tool_currency_convert()
    test_database_cache_service()
    test_reverse_geocode_service()
    test_swiggy_mcp_integration()
    test_copilot_dineout_direct_url_generation()
    test_trip_share_and_fork_system()
    test_dual_layer_user_memory()
    print("✅ All 19 test suites passed successfully!")
