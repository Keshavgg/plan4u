"""Plan4U AI Backend Application Entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.bookings import router as bookings_router
from app.config import settings

app = FastAPI(
    title="Plan4U AI Backend",
    description="Multi-Agent AI travel planning, real-time live copilot, GDS/TBO bookings, and group split engine.",
    version="1.0.0",
)

# Enable CORS for Web frontend, mobile apps, and developer clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(router)
app.include_router(bookings_router)


@app.on_event("startup")
def warm_ai_clients():
    """Creating the Gemini and Claude clients takes seconds; do it in the background at startup so the first
    chat message does not pay for it."""
    import threading

    def warm():
        try:
            from app.agent.subagents.copilot_agent import _anthropic_client, _gemini_client
            if settings.GEMINI_API_KEY:
                _gemini_client()
            if settings.ANTHROPIC_API_KEY:
                _anthropic_client()
        except Exception as e:
            print(f"[Startup] AI client warm-up skipped: {e}")

    threading.Thread(target=warm, daemon=True, name="warm-ai-clients").start()


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def root():
    return {
        "status": "healthy",
        "service": "Plan4U AI Travel Engine API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_check": "/api/v1/health",
        "panels": {
            "panel_1_planner": "/api/v1/planner/generate",
            "panel_2_companion": "/api/v1/companion/chat",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
