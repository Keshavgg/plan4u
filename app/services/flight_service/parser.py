"""Parses raw TBO and supplier responses into Pydantic FlightOption models."""
from typing import Dict, Any, List
from app.schemas.flight import FlightOption, FlightSegment, FlightProvider, FlightSearchResult

# Airline logos & names lookup
AIRLINE_METADATA = {
    "6E": {"name": "IndiGo", "logo": "https://images.kiwi.com/airlines/64/6E.png", "is_lcc": True},
    "AI": {"name": "Air India", "logo": "https://images.kiwi.com/airlines/64/AI.png", "is_lcc": False},
    "UK": {"name": "Vistara", "logo": "https://images.kiwi.com/airlines/64/UK.png", "is_lcc": False},
    "QP": {"name": "Akasa Air", "logo": "https://images.kiwi.com/airlines/64/QP.png", "is_lcc": True},
    "SG": {"name": "SpiceJet", "logo": "https://images.kiwi.com/airlines/64/SG.png", "is_lcc": True},
}


def parse_tbo_search_response(
    raw_data: Dict[str, Any],
    origin: str,
    destination: str,
    departure_date: str,
) -> FlightSearchResult:
    """Transforms raw TBO Air JSON response into typed FlightSearchResult."""
    response_block = raw_data.get("Response", {})
    trace_id = response_block.get("TraceId", "")
    results = response_block.get("Results", [])

    flight_options: List[FlightOption] = []

    # TBO results can be nested list: [[Segment1, Segment2], ...]
    flat_results = results[0] if results and isinstance(results[0], list) else results

    for idx, item in enumerate(flat_results):
        segments_raw = item.get("Segments", [[]])[0]
        if not segments_raw:
            continue

        first_seg = segments_raw[0]
        last_seg = segments_raw[-1]
        
        carrier_code = first_seg.get("Airline", {}).get("AirlineCode", "6E")
        airline_meta = AIRLINE_METADATA.get(carrier_code, {"name": first_seg.get("Airline", {}).get("AirlineName", "Airline"), "logo": None, "is_lcc": True})

        # Process Segments
        parsed_segments: List[FlightSegment] = []
        for seg in segments_raw:
            airline_info = seg.get("Airline", {})
            origin_info = seg.get("Origin", {})
            dest_info = seg.get("Destination", {})

            parsed_segments.append(
                FlightSegment(
                    airline_code=airline_info.get("AirlineCode", carrier_code),
                    airline_name=airline_meta["name"],
                    airline_logo=airline_meta.get("logo"),
                    flight_number=f"{airline_info.get('AirlineCode', '')}-{airline_info.get('FlightNumber', '')}",
                    aircraft=seg.get("Craft"),
                    origin=origin_info.get("Airport", {}).get("AirportCode", origin),
                    origin_terminal=origin_info.get("Airport", {}).get("Terminal"),
                    destination=dest_info.get("Airport", {}).get("AirportCode", destination),
                    destination_terminal=dest_info.get("Airport", {}).get("Terminal"),
                    departure_time=origin_info.get("DepTime", ""),
                    arrival_time=dest_info.get("ArrTime", ""),
                    duration=f"{seg.get('Duration', 120)}m",
                    seats_left=seg.get("NoOfSeatAvailable"),
                )
            )

        # Fare details
        fare = item.get("Fare", {})
        published_price = float(fare.get("PublishedPrice", 5500.0))
        base_fare = float(fare.get("BaseFare", published_price * 0.8))
        tax = float(fare.get("Tax", published_price - base_fare))

        flight_options.append(
            FlightOption(
                id=f"tbo_{trace_id[:8]}_{item.get('ResultIndex', idx)}",
                provider=FlightProvider.TBO,
                trace_id=trace_id,
                result_index=str(item.get("ResultIndex", idx)),
                airline_name=airline_meta["name"],
                airline_code=carrier_code,
                airline_logo=airline_meta.get("logo"),
                is_lcc=airline_meta.get("is_lcc", True),
                is_refundable=item.get("IsRefundable", False),
                origin=origin.upper(),
                destination=destination.upper(),
                departure_time=parsed_segments[0].departure_time,
                arrival_time=parsed_segments[-1].arrival_time,
                total_duration=f"{item.get('Duration', 135)}m",
                stops=len(parsed_segments) - 1,
                segments=parsed_segments,
                cabin_baggage=item.get("CabinBaggage", "7 Kg"),
                checkin_baggage=first_seg.get("Baggage", "15 Kg"),
                base_fare=base_fare,
                taxes_and_surcharges=tax,
                published_fare=published_price,
                currency="INR",
            )
        )

    return FlightSearchResult(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        trace_id=trace_id,
        provider=FlightProvider.TBO,
        options=flight_options,
        total_found=len(flight_options),
    )
