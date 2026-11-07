"""Application Configuration loaded from environment variables."""
import os
from pathlib import Path

# Helper to load .env manually if python-dotenv is not installed
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)
    except ImportError:
        # Fallback basic parser for key=value lines
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


class Settings:
    ENV: str = os.getenv("ENV", "development")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Gemini, Anthropic Claude & Exa AI
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    EXA_API_KEY: str = os.getenv("EXA_API_KEY", "")
    EXA_TIMEOUT_SECONDS: float = float(os.getenv("EXA_TIMEOUT_SECONDS", "8"))
    # Event catalog: how long a city's events/movies are served before a background refresh.
    EVENTS_CACHE_TTL_SECONDS: int = int(os.getenv("EVENTS_CACHE_TTL_SECONDS", "43200"))   # 12 h
    MOVIES_CACHE_TTL_SECONDS: int = int(os.getenv("MOVIES_CACHE_TTL_SECONDS", "86400"))   # 24 h
    # Hard cap on Exa searches per day (UTC), so a bug or traffic spike cannot run up the bill.
    EXA_MAX_CALLS_PER_DAY: int = int(os.getenv("EXA_MAX_CALLS_PER_DAY", "200"))
    # Smaller cap for free-text searches ("Zakir Khan", "pottery workshop"), since anyone can type a new one.
    EXA_MAX_CUSTOM_SEARCHES_PER_DAY: int = int(os.getenv("EXA_MAX_CUSTOM_SEARCHES_PER_DAY", "50"))
    EXA_EVENT_DOMAINS: list = [
        d.strip() for d in os.getenv(
            "EXA_EVENT_DOMAINS",
            "bookmyshow.com,insider.in,district.in,skillboxes.com,skillbox.co,zomato.com",
        ).split(",") if d.strip()
    ]

    # Flight APIs
    AMADEUS_CLIENT_ID: str = os.getenv("AMADEUS_CLIENT_ID", "")
    AMADEUS_CLIENT_SECRET: str = os.getenv("AMADEUS_CLIENT_SECRET", "")
    GALILEO_API_URL: str = os.getenv("GALILEO_API_URL", "")
    GALILEO_TARGET_BRANCH: str = os.getenv("GALILEO_TARGET_BRANCH", "")
    GALILEO_CREDENTIALS: str = os.getenv("GALILEO_CREDENTIALS", "")
    INDIGO_AGENT_ID: str = os.getenv("INDIGO_AGENT_ID", "")
    INDIGO_API_KEY: str = os.getenv("INDIGO_API_KEY", "")

    # TBO Hotels API
    TBO_USERNAME: str = os.getenv("TBO_USERNAME", "")
    TBO_PASSWORD: str = os.getenv("TBO_PASSWORD", "")
    TBO_HOTEL_USERNAME: str = os.getenv("TBO_HOTEL_USERNAME", "")
    TBO_HOTEL_PASSWORD: str = os.getenv("TBO_HOTEL_PASSWORD", "")
    TBO_CLIENT_ID: str = os.getenv("TBO_CLIENT_ID", "ApiIntegrationNew")
    TBO_API_URL: str = os.getenv(
        "TBO_API_URL", "http://api.tbotechnology.net/HotelAPI_V10/HotelService.svc"
    )

    # Restaurant / Dining API
    RESTAURANT_API_BASE_URL: str = os.getenv("RESTAURANT_API_BASE_URL", "")
    RESTAURANT_API_KEY: str = os.getenv("RESTAURANT_API_KEY", "")

    # Payments
    PAYMENT_KEY_ID: str = os.getenv("PAYMENT_KEY_ID", "")
    PAYMENT_KEY_SECRET: str = os.getenv("PAYMENT_KEY_SECRET", "")

    # Production Database (Hostinger MySQL / PostgreSQL / SQLite)
    # Default is SQLite (data_store/plan4u.db) for zero-config local & VPS deployment.
    # For Hostinger MySQL, set DATABASE_URL=mysql://user:pass@localhost:3306/dbname
    # or set DB_TYPE=mysql, DB_HOST=localhost, DB_USER=..., DB_PASSWORD=..., DB_NAME=...
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    DB_PATH: str = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "data_store" / "plan4u.db"))
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "plan4u")

    # Swiggy Model Context Protocol (MCP) Stack
    # Leave SWIGGY_CLIENT_ID empty to self-register via Dynamic Client Registration.
    SWIGGY_CLIENT_ID: str = os.getenv("SWIGGY_CLIENT_ID", "")
    SWIGGY_MCP_BASE_URL: str = os.getenv("SWIGGY_MCP_BASE_URL", "https://mcp.swiggy.com")
    SWIGGY_FRONTEND_URL: str = os.getenv("SWIGGY_FRONTEND_URL", "http://localhost:3000")
    SWIGGY_REDIRECT_URI: str = os.getenv(
        "SWIGGY_REDIRECT_URI", "http://localhost:8000/api/v1/swiggy/oauth/callback"
    )
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt stored Swiggy tokens.
    # Required when ENV=production; in development a key file is generated next to the DB.
    SWIGGY_TOKEN_ENCRYPTION_KEY: str = os.getenv("SWIGGY_TOKEN_ENCRYPTION_KEY", "")
    # App user whose connected Swiggy account serves read-only discovery (search, details,
    # slots) before an end user has connected their own. Bookings never use it.
    SWIGGY_SERVICE_USER_ID: str = os.getenv("SWIGGY_SERVICE_USER_ID", "")
    # Restaurant search results are shared between users for this long, then refreshed in the background.
    SWIGGY_SEARCH_TTL_SECONDS: int = int(os.getenv("SWIGGY_SEARCH_TTL_SECONDS", "21600"))  # 6 h
    # Hard cap on Swiggy restaurant searches per day (UTC). Cached data is still served after it.
    SWIGGY_MAX_SEARCHES_PER_DAY: int = int(os.getenv("SWIGGY_MAX_SEARCHES_PER_DAY", "500"))

    # Firebase Auth: ID tokens are verified against this project id.
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")

    # Table bookings: a prepared booking must be confirmed within the TTL, and each user is
    # capped per day so a bug or abuse cannot spam reservations on their Swiggy account.
    BOOKING_CONFIRM_TTL_SECONDS: int = int(os.getenv("BOOKING_CONFIRM_TTL_SECONDS", "600"))
    BOOKING_MAX_PER_DAY: int = int(os.getenv("BOOKING_MAX_PER_DAY", "10"))


settings = Settings()
