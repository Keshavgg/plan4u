# Plan4U AI Backend — Complete API & cURL Collection

This guide provides ready-to-run `curl` requests for all **Plan4U** endpoints across:
1. **Two Core Panels**: Panel 1 (Master Pre-Trip Planner) & Panel 2 (Live In-Trip Copilot)
2. **MakeMyTrip-Style Manual Inventory Exploration & Booking** (Flights, Hotels, Restaurants, Attractions, Live Events)
3. **Auto-Fetch GPS Nearby Explorer**
4. **Autonomous AI Subagent Smart Tools**

Server default base URL: `http://localhost:8000`

---

## 🌟 1. Core Panels

### Panel 1: Master Pre-Trip Planner (`POST /api/v1/planner/generate`)
Synthesizes flights, hotels, monuments, dining, budget constraints, and 15-minute Razorpay hold.
```bash
curl -X POST "http://localhost:8000/api/v1/planner/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "DEL",
    "destination": "Jaipur",
    "start_date": "2026-11-15",
    "end_date": "2026-11-17",
    "total_budget": 35000,
    "traveler_count": 2,
    "interests": ["heritage", "cafes", "photography"]
  }'
```

### Panel 2: Live In-Trip Companion / Copilot (`POST /api/v1/companion/chat`)
Real-time GPS-aware concierge handling food cravings, weather pivots, live events, and 1-click Fast-Track digital passes.
```bash
curl -X POST "http://localhost:8000/api/v1/companion/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "Bhai Hawa Mahal ke paas mast lassi ya kachori khilao",
    "current_lat": 26.9239,
    "current_lng": 75.8267,
    "current_time_str": "04:30 PM"
  }'
```

---

## 📍 2. Master GPS Nearby Explorer

### Aggregated Nearby (`GET /api/v1/explore/nearby`)
Returns nearby hotels, restaurants, monuments, and live events in a single call based on device GPS.
```bash
curl -X GET "http://localhost:8000/api/v1/explore/nearby?lat=26.9239&lng=75.8267&radius_km=3.0&city=Jaipur"
```

---

## ✈️ 3. Flights (MakeMyTrip / Goibibo Style)

### Flight Search with Filters (`POST /api/v1/flights/search`)
```bash
curl -X POST "http://localhost:8000/api/v1/flights/search" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "DEL",
    "destination": "JAI",
    "departure_date": "2026-11-15",
    "adults": 2,
    "max_price": 6000,
    "sort_by": "price_asc"
  }'
```

### Fare Quote (`POST /api/v1/flights/quote`)
```bash
curl -X POST "http://localhost:8000/api/v1/flights/quote" \
  -H "Content-Type: application/json" \
  -d '{
    "flight_id": "fl_del_jai_01",
    "trace_id": "tr_6e_del_jai_99",
    "result_index": "1"
  }'
```

### Seat Map & SSR Ancillaries (`POST /api/v1/flights/seat-map`)
```bash
curl -X POST "http://localhost:8000/api/v1/flights/seat-map" \
  -H "Content-Type: application/json" \
  -d '{
    "flight_id": "fl_del_jai_01",
    "trace_id": "tr_6e_del_jai_99",
    "result_index": "1"
  }'
```

### 15-Minute Flight PNR Hold (`POST /api/v1/flights/hold`)
```bash
curl -X POST "http://localhost:8000/api/v1/flights/hold" \
  -H "Content-Type: application/json" \
  -d '{
    "flight_id": "fl_del_jai_01",
    "trace_id": "tr_6e_del_jai_99",
    "result_index": "1",
    "passengers": [
      {
        "title": "Mr",
        "first_name": "Amit",
        "last_name": "Sharma",
        "gender": "Male",
        "date_of_birth": "1995-05-12",
        "email": "amit@example.com",
        "phone": "9876543210"
      }
    ]
  }'
```

---

## 🏨 4. Hotels & Stays

### Search Hotels with Star & Budget Filters (`POST /api/v1/hotels/search`)
```bash
curl -X POST "http://localhost:8000/api/v1/hotels/search" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Jaipur",
    "check_in_date": "2026-11-15",
    "check_out_date": "2026-11-17",
    "min_star_rating": 3,
    "max_price": 5000
  }'
```

### Auto-Fetch Nearby Hotels via Live GPS (`GET /api/v1/hotels/nearby`)
```bash
curl -X GET "http://localhost:8000/api/v1/hotels/nearby?lat=26.9239&lng=75.8267&city=Jaipur&radius_km=5.0"
```

### Hotel Details (`GET /api/v1/hotels/{hotel_code}`)
```bash
curl -X GET "http://localhost:8000/api/v1/hotels/tbo_jai_001"
```

### Hotel Pre-Book Price & Room Lock (`POST /api/v1/hotels/prebook`)
```bash
curl -X POST "http://localhost:8000/api/v1/hotels/prebook" \
  -H "Content-Type: application/json" \
  -d '{
    "hotel_code": "tbo_jai_001",
    "room_type_code": "DLX-01",
    "check_in_date": "2026-11-15",
    "check_out_date": "2026-11-17"
  }'
```

---

## 🍽️ 5. Restaurants & Cafes

### Search Restaurants with Cuisine & Price Band (`POST /api/v1/places/restaurants/search`)
```bash
curl -X POST "http://localhost:8000/api/v1/places/restaurants/search" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Jaipur",
    "cuisines": ["Rajasthani Thali"],
    "is_pure_veg": true,
    "min_rating": 4.0
  }'
```

### Auto-Fetch Nearby Restaurants (`GET /api/v1/places/restaurants/nearby`)
```bash
curl -X GET "http://localhost:8000/api/v1/places/restaurants/nearby?lat=26.9239&lng=75.8267&radius_meters=3000"
```

---

## 🏛️ 6. Monuments & Attractions

### Search Attractions with Entry Fee Filter (`POST /api/v1/places/attractions/search`)
```bash
curl -X POST "http://localhost:8000/api/v1/places/attractions/search" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Jaipur",
    "max_entry_fee": 300,
    "sort_by": "rating_desc"
  }'
```

### Auto-Fetch Nearby Monuments (`GET /api/v1/places/attractions/nearby`)
```bash
curl -X GET "http://localhost:8000/api/v1/places/attractions/nearby?lat=26.9239&lng=75.8267&radius_meters=4000"
```

---

## 🎟️ 7. Live Events & Shows (BookMyShow / Insider)

### Search Events (`GET /api/v1/events/search`)
```bash
curl -X GET "http://localhost:8000/api/v1/events/search?city=Jaipur&category=music"
```

### Auto-Fetch Nearby Events (`GET /api/v1/events/nearby`)
```bash
curl -X GET "http://localhost:8000/api/v1/events/nearby?lat=26.9239&lng=75.8267&city=Jaipur"
```

---

## ⚡ 8. Subagent Smart Tools

### Deal Hunter & Red-Eye Flight Tradeoffs (`POST /api/v1/tools/flights/tradeoffs`)
```bash
curl -X POST "http://localhost:8000/api/v1/tools/flights/tradeoffs" \
  -H "Content-Type: application/json" \
  -d '{
    "flights": [
      {
        "id": "f1",
        "airline_name": "IndiGo",
        "airline_code": "6E",
        "origin": "DEL",
        "destination": "JAI",
        "departure_time": "02:15 AM",
        "arrival_time": "03:15 AM",
        "total_duration": "1h 00m",
        "published_fare": 3800.0
      },
      {
        "id": "f2",
        "airline_name": "Akasa Air",
        "airline_code": "QP",
        "origin": "DEL",
        "destination": "JAI",
        "departure_time": "07:30 AM",
        "arrival_time": "08:35 AM",
        "total_duration": "1h 05m",
        "published_fare": 4350.0
      }
    ]
  }'
```

### Zero-Backtrack Spatial Clustering (`POST /api/v1/tools/itinerary/cluster`)
Groups attractions into tight geographic clusters saving ~90 mins of traffic daily.
```bash
curl -X POST "http://localhost:8000/api/v1/tools/itinerary/cluster" \
  -H "Content-Type: application/json" \
  -d '{
    "places": [
      {"name": "Hawa Mahal", "latitude": 26.9239, "longitude": 75.8267},
      {"name": "Jantar Mantar", "latitude": 26.9248, "longitude": 75.8246},
      {"name": "Amber Fort", "latitude": 26.9855, "longitude": 75.8513},
      {"name": "Nahargarh Fort", "latitude": 26.9378, "longitude": 75.8156}
    ],
    "days_count": 2
  }'
```

### Emergency Weather / Rain Reroute (`POST /api/v1/tools/companion/reroute`)
Pivots from outdoor forts to covered museums & indoor cafes instantly when rain or extreme heat strikes.
```bash
curl -X POST "http://localhost:8000/api/v1/tools/companion/reroute" \
  -H "Content-Type: application/json" \
  -d '{
    "current_lat": 26.9239,
    "current_lng": 75.8267,
    "reason": "heavy_rain",
    "time_of_day": "03:30 PM"
  }'
```

### Event-Anchored Weekend Planner (`POST /api/v1/tools/planner/event-anchored`)
```bash
curl -X POST "http://localhost:8000/api/v1/tools/planner/event-anchored" \
  -H "Content-Type: application/json" \
  -d '{
    "event_query": "Zakir Khan Live",
    "city": "Delhi",
    "origin_city": "BOM",
    "departure_date": "2026-11-20"
  }'
```

### Group Debt Settlement with UPI Links (`POST /api/v1/tools/group-split/payment-links`)
Generates clickable `upi://pay` links, Razorpay orders, and WhatsApp share templates.
```bash
curl -X POST "http://localhost:8000/api/v1/tools/group-split/payment-links" \
  -H "Content-Type: application/json" \
  -d '{
    "expenses": [
      {
        "title": "Dinner at Chokhi Dhani",
        "amount": 3000,
        "paid_by": "Amit",
        "split_among": ["Amit", "Rahul", "Priya"]
      }
    ],
    "upi_vpa": "amit@okhdfcbank"
  }'
```

### Transport Fare Estimator (`POST /api/v1/tools/transport/estimate`)
Computes road distance, drive duration, Cab (Uber/Ola), Auto-rickshaw, and Metro fares.
```bash
curl -X POST "http://localhost:8000/api/v1/tools/transport/estimate" \
  -H "Content-Type: application/json" \
  -d '{
    "origin_lat": 26.9239,
    "origin_lng": 75.8267,
    "dest_lat": 26.9855,
    "dest_lng": 75.8513,
    "city": "Jaipur"
  }'
```

### Destination Packing Checklist Generator (`POST /api/v1/tools/packing/checklist`)
```bash
curl -X POST "http://localhost:8000/api/v1/tools/packing/checklist" \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "Jaipur",
    "duration_days": 3,
    "season_or_month": "November",
    "activities": ["sightseeing", "fine dining"]
  }'
```

### Real-Time Currency Converter (`GET /api/v1/tools/currency/convert`)
```bash
curl -X GET "http://localhost:8000/api/v1/tools/currency/convert?amount=100&from_curr=USD&to_curr=INR"
```
