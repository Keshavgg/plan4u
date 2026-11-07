# Plan4U Frontend Portal

A dual-mode testing and chat interface for **Plan4U AI Travel Engine**:
1. **Mode 1: Long Itinerary Plan (Panel 1 Master Planner)**
   - Destination, Dates, Budget, and Travel Vibes selector
   - Day-by-day rich itinerary cards (Flights, 10k Hotels, Monuments, Dining)
   - Real-time 15-minute Seat Hold and Room Rate Lock buttons with Razorpay order simulation
   - Pro travel tips (deal hunter savings, zero-backtrack traffic savings, golden hour sunset)
2. **Mode 2: Live In-Trip Copilot (Panel 2 Companion)**
   - Real-time chatting interface with live GPS coordinates simulation
   - Quick action prompt chips (Street Food Cravings, Rain Emergency Reroute, Fast-Track Monument Pass, Live Events & Gigs)
   - Actionable recommendation cards with table reservations and 1-click passes

## How to Run:

Start the frontend on port 3000:
```bash
python3 server.py
```
Then open [http://localhost:3000](http://localhost:3000) in your browser.

Ensure the backend server is running on port 8000:
```bash
cd ../plan4u_backend
python3 app/main.py
```
