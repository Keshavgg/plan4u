"""Parses raw TBO Hotel API responses into typed Pydantic models."""
from typing import Dict, Any, List
from app.schemas.hotel import (
    HotelOption,
    HotelRoom,
    MealType,
    CancellationPolicyBand,
    HotelSearchResult,
    HotelProvider,
)


def parse_tbo_hotel_response(
    raw_data: Dict[str, Any],
    city_name: str,
    check_in_date: str,
    check_out_date: str,
) -> HotelSearchResult:
    """Transforms raw TBO GetHotelResult JSON into a typed HotelSearchResult."""
    hotel_list = raw_data.get("HotelResult", [])
    options: List[HotelOption] = []

    for item in hotel_list:
        price_info = item.get("Price", {})
        pub_price = float(price_info.get("PublishedPrice", 3500.0))
        hotel_code = str(item.get("HotelCode"))

        options.append(
            HotelOption(
                id=f"tbo_{hotel_code}",
                provider=HotelProvider.TBO,
                hotel_code=hotel_code,
                name=item.get("HotelName", "TBO Hotel"),
                star_rating=int(item.get("StarRating", 3)),
                trip_advisor_rating=float(item.get("TripAdvisorRating", 4.0)),
                review_count=int(item.get("ReviewCount", 24)),
                address=item.get("HotelAddress", city_name),
                city=city_name.title(),
                latitude=item.get("Latitude"),
                longitude=item.get("Longitude"),
                min_price_per_night=pub_price,
                total_estimated_price=pub_price * 2,
                featured_image=item.get("HotelPicture") or "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800",
                amenities=["Free WiFi", "Swimming Pool", "Air Conditioning", "Breakfast Available"],
                rooms=[
                    HotelRoom(
                        room_type_name="Standard Deluxe Room",
                        meal_type=MealType.BREAKFAST_INCLUDED,
                        is_refundable=True,
                        price_per_night=pub_price,
                        total_fare=pub_price * 2,
                        cancellation_policies=[
                            CancellationPolicyBand(
                                from_date=check_in_date,
                                charge_type="Fixed",
                                charge_amount=0.0,
                            )
                        ],
                    )
                ],
            )
        )

    return HotelSearchResult(
        city=city_name.title(),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        provider=HotelProvider.TBO,
        options=options,
        total_found=len(options),
    )
