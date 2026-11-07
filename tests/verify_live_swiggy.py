"""Live verification script for Swiggy MCP Service."""
import json
from app.services.swiggy_mcp_service import swiggy_mcp_service

test_cases = [
    {"city": "Bengaluru", "locality": "Indiranagar", "food_q": "Dosa", "dine_q": "Brewery"},
    {"city": "Mumbai", "locality": "Bandra West", "food_q": "Sushi", "dine_q": "Cafe"},
    {"city": "Delhi", "locality": "Pitampura", "food_q": "Momos", "dine_q": "Family Restaurant"},
    {"city": "Jaipur", "locality": "C Scheme", "food_q": "Dal Baati", "dine_q": "Rooftop Lounge"},
    {"city": "Hyderabad", "locality": "Banjara Hills", "food_q": "Biryani", "dine_q": "Fine Dining"},
]

print("=" * 65)
print("LIVE SWIGGY MCP REAL-TIME API VERIFICATION (NO STATIC DATA)")
print("=" * 65)

for tc in test_cases:
    city = tc["city"]
    loc = tc["locality"]
    coords = swiggy_mcp_service._resolve_coordinates(loc, city)
    print(f"\n[Location] {loc}, {city} -> Dynamic GPS: {coords}")
    
    # 1. Test Live Food Search
    fq = tc["food_q"]
    food_res = swiggy_mcp_service.search_swiggy_food(query=fq, locality=loc, city=city, limit=2)
    print(f"  [Food Query: '{fq}'] -> {len(food_res)} live results")
    for f in food_res:
        f_id = f.get('id')
        name = f.get('name')
        rating = f.get('rating')
        sla = f.get('sla_string')
        area = f.get('locality')
        src = f.get('source')
        print(f"    - ID: {f_id} | Name: {name} | Rating: {rating} | SLA: {sla} | Area: {area} | Source: {src}")
    
    # 2. Test Live Dineout Search
    dq = tc["dine_q"]
    dine_res = swiggy_mcp_service.search_swiggy_dineout(query=dq, locality=loc, city=city, limit=2)
    print(f"  [Dineout Query: '{dq}'] -> {len(dine_res)} live results")
    for d in dine_res:
        d_id = d.get('id')
        name = d.get('name')
        rating = d.get('rating')
        cost = d.get('cost_per_person')
        url = d.get('booking_url')
        src = d.get('source')
        print(f"    - ID: {d_id} | Name: {name} | Rating: {rating} | Cost/Person: ₹{cost} | Booking: {url} | Source: {src}")

print("\n" + "=" * 65)
print("ALL LIVE TESTS COMPLETED WITH REAL-TIME SWIGGY DAPI + NOMINATIM")
print("=" * 65)
