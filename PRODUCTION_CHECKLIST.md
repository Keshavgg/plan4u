# Plan4U Backend — Production Switch Checklist & Notes

## 🚨 MANDATORY USER INSTRUCTION:
**Jab real keys (TBO, Galileo, Places, Razorpay) provide ho jayein:**
- [ ] Saare services (`hotel_service.py`, `flight_service.py`, `places_service.py`) se `_get_mock_*` fallback functions poori tarah remove kar dene hain.
- [ ] Strict Live Mode enforce karna hai: Agar supplier ka response na mile ya credentials invalid hon, toh fake/mock data dikhane ke bajaye seedha proper API error throw karna hai (`503 Service Unavailable` / `NOT_CONFIGURED`).
- [ ] `config.py` me `ENV=production` set karna hai.

---

## 🔑 Keys to Plug in `.env`:
1. `TBO_USERNAME` & `TBO_PASSWORD`
2. `TBO_CLIENT_ID` (`ApiIntegrationNew`)
3. `TBO_HOTEL_USERNAME` & `TBO_HOTEL_PASSWORD`
4. `TRAVELPORT_USERNAME`, `TRAVELPORT_PASSWORD`, `TRAVELPORT_TARGET_BRANCH`, `TRAVELPORT_PCC`
5. `GEMINI_API_KEY`
6. `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`
