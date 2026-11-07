# Plan4U — Complete AI Engine & Full Manual Travel Booking Backend

Plan4U provides both **Autonomous AI Trip Planning & Companionship** and **100% MakeMyTrip / Zomato / BookMyShow-Style Manual Exploration & Direct Booking** across Flights, Hotels, Restaurants, Monuments, and Live Events.

---

## 🧭 System Overview

```
                      ┌───────────────────────────────────────────────┐
                      │              Plan4U Client UI                 │
                      │        (Web / iOS / Android Apps)             │
                      └───────┬───────────────────────────────┬───────┘
                              │                               │
            ┌─────────────────▼──────────────┐   ┌────────────▼─────────────────┐
            │        AI Multi-Agent          │   │      Manual Exploration      │
            │          Two Panels            │   │      & Direct Booking        │
            ├────────────────────────────────┤   ├──────────────────────────────┤
            │ Panel 1: Master Pre-Trip Plan  │   │ ✈️ Flights (Filter, SSR, PNR) │
            │ Panel 2: Live In-Trip Copilot  │   │ 🏨 Hotels (GPS Nearby, PreBk) │
            │ 🎬 Clip2Trip (Reel Extraction) │   │ 🍽️ Restaurants (Cuisine, GPS)│
            │ 💸 Splitwise Group Split       │   │ 🏛️ Monuments (Tickets, Sights)│
            │ ⚡ Fast-Track QR Passes        │   │ 🎟️ Live Events (BMS Links)   │
            └────────────────────────────────┘   │ 📍 Master /explore/nearby    │
                                                 └──────────────────────────────┘
```

---

## 📍 1. Unified Master "Explore Nearby" (Auto-Fetch via GPS)

When the user opens the app or arrives at a landmark, **one single call** auto-fetches everything around their live GPS coordinates:

### `GET /api/v1/explore/nearby`
**Query Parameters:**
- `lat`: User's live GPS Latitude (e.g. `28.6315`)
- `lng`: User's live GPS Longitude (e.g. `77.2167`)
- `city`: Current city (e.g. `Delhi`, `Jaipur`, `Goa`)
- `radius_km`: Search radius in km (default `5.0`)

**Response:**
```json
{
  "center": {"lat": 28.6315, "lng": 77.2167},
  "city": "Delhi",
  "radius_km": 5.0,
  "total_nearby_items": 8,
  "hotels": [
    {
      "name": "Grand Delhi Palace Hotel",
      "star_rating": 4,
      "min_price_per_night": 4200.0,
      "address": "City Center, Delhi",
      "amenities": ["Swimming Pool", "Free Breakfast", "Gym"]
    }
  ],
  "restaurants": [
    {
      "name": "Karim's Historic Old Delhi",
      "cuisines": ["Mughlai", "Mutton Burra", "Kebabs"],
      "estimated_cost_per_person": 600.0,
      "distance_meters": 2100,
      "rating": 4.7
    }
  ],
  "attractions": [
    {
      "name": "Humayun's Tomb",
      "category": "heritage",
      "entry_fee": 50.0,
      "distance_meters": 4200,
      "best_time_slot": "Late Afternoon"
    }
  ],
  "live_events": [
    {
      "title": "Zakir Khan Live - Standup Special",
      "category": "comedy",
      "venue": "Kedarnath Sahni Auditorium, Connaught Place",
      "date_time": "Saturday, 7:30 PM",
      "price_range_inr": "₹999 - ₹2,499",
      "distance_km": 0.5,
      "booking_provider": "BookMyShow",
      "booking_url": "https://in.bookmyshow.com/explore/comedy-shows-delhi-ncr"
    }
  ]
}
```

---

## ✈️ 2. Flights Manual Search & Booking (MakeMyTrip Style)

### `POST /api/v1/flights/search`
Search flights with comprehensive manual filters:
- **Price**: `min_price`, `max_price`
- **Airlines**: `airlines` array (e.g. `["6E", "AI", "QP"]`)
- **Stops**: `max_stops` (0 for non-stop, 1 for 1 stop)
- **Refundability**: `is_refundable` (true/false)
- **Departure Window**: `departure_time_window` (`early_morning`, `morning`, `afternoon`, `evening`)
- **Sorting**: `sort_by` (`price_asc`, `price_desc`, `duration_asc`, `departure_asc`)

### `POST /api/v1/flights/quote`
Fare lock validation before checkout.

### `POST /api/v1/flights/rules`
MMT-style cancellation penalty fee table and date-change charges.

### `POST /api/v1/flights/seat-map` (SSR)
Hot meals selection (Veg/Non-Veg) and extra baggage tiers (+5kg, +10kg).

### `POST /api/v1/flights/hold`
Places live PNR reservation hold on airline GDS with Passenger details (Name, DOB, Gender, PAN Card, GST) + 15-minute Razorpay payment session.

---

## 🏨 3. Hotels Manual Search & Booking

### `POST /api/v1/hotels/search`
Filter by:
- `min_price` and `max_budget_per_night`
- `min_star_rating` (3, 4, 5 stars)
- `preferred_amenities` (`swimming_pool`, `free_breakfast`, `spa`, `wifi`, `beachfront`, `rooftop`)
- `sort_by` (`price_asc`, `price_desc`, `rating_desc`, `distance_asc`)

### `GET /api/v1/hotels/nearby`
Auto-fetches hotels near user's GPS coordinates (`lat`, `lng`, `radius_km`) sorted by distance.

### `GET /api/v1/hotels/{hotel_code}`
Photo gallery, amenities, house rules.

### `POST /api/v1/hotels/prebook`
Price lock room hold for 15 minutes.

---

## 🍽️ 4. Restaurants & Cafes Manual Search

### `POST /api/v1/places/restaurants/search`
Filter by:
- `cuisines` (`North Indian`, `Rajasthani`, `Seafood`, `Italian`, `Cafe`, etc.)
- `price_band` (`₹`, `₹₹`, `₹₹₹`, `₹₹₹₹`)
- `min_price` and `max_price`
- `min_rating` (e.g. 4.0+)
- `category` (`restaurant`, `cafe`, `bar_nightlife`)
- `sort_by` (`distance_asc`, `rating_desc`, `price_asc`)

### `GET /api/v1/places/restaurants/nearby`
Auto-fetch food spots near live GPS (`lat`, `lng`, `radius_meters`) with distance and walking time.

---

## 🏛️ 5. Monuments & Attractions Manual Search

### `POST /api/v1/places/attractions/search`
Filter by:
- `category` (`monument`, `heritage`, `museum`, `viewpoint`, `activity`)
- `max_entry_fee` (in INR)
- `sort_by` (`rating_desc`, `distance_asc`, `price_asc`)

### `GET /api/v1/places/attractions/nearby`
Auto-fetch heritage sights and photo spots near live GPS coordinates.

---

## 🎟️ 6. Live Events, Comedy & Nightlife

### `GET /api/v1/events/search`
Filter by:
- `city`
- `category` (`music`, `comedy`, `festival`, `nightlife`, `art`)
- `timeframe` (`today`, `tomorrow`, `this weekend`, `this week`)
- `min_price`, `max_price`
- `is_free` (Free entry events only)
- `sort_by` (`popularity`, `price_asc`, `price_desc`)

### `GET /api/v1/events/nearby`
Auto-fetch events near user's live GPS coordinates with direct BookMyShow / Paytm Insider booking links.

---

## ⚡ 7. Specialized Smart Tools & Superpowers (`/api/v1/tools/...`)

These work both as **manual high-utility endpoints** and as **tools called by subagents**:

| Endpoint | Method | What it Does / Superpower |
| :--- | :--- | :--- |
| `/api/v1/tools/flights/tradeoffs` | `POST` | Evaluates cheapest vs fastest, detects 2 AM red-eye cab surcharges, and spots ₹2,000+ time-shift savings. |
| `/api/v1/tools/itinerary/cluster` | `POST` | Smart spatial clustering grouping spots into tight geographical days, saving ~90 mins of traffic. |
| `/api/v1/tools/companion/reroute` | `POST` | Real-time weather (rain/heat) & closure rerouting with instant indoor & covered comfort pivots. |
| `/api/v1/tools/planner/event-anchored` | `POST` | Designs an entire weekend getaway anchored around an event, concert (Zakir Khan, Diljit), or comedy show. |
| `/api/v1/tools/group-split/payment-links` | `POST` | Generates direct clickable UPI deep-links (`upi://pay`), Razorpay links, and WhatsApp share templates. |
| `/api/v1/tools/transport/estimate` | `POST` | Computes road distance, drive duration, Cab (Uber/Ola), Auto-rickshaw, and Metro fares. |
| `/api/v1/tools/packing/checklist` | `POST` | Generates a destination-, climate-, and activity-aware smart packing checklist. |
| `/api/v1/tools/weather/forecast` | `GET` | Destination climatology, temperatures, sunrise/sunset times, and photography golden hours. |
| `/api/v1/tools/currency/convert` | `GET` | Multi-currency FX converter with fee-saving advice for international travelers. |

---

## 🚀 Running the Server

```bash
cd /Users/keshavjindal/.gemini/antigravity/scratch/plan4u_backend
uvicorn app.main:app --reload --port 8000
```
Interactive Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
