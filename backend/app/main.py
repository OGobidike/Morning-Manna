

# import the FastAPI class from the fastapi module
from fastapi import FastAPI

from app.config import settings
from app.logs import configure_logging, log_requests
from app.routers import events, plans, readings, today, translations, users

# creates application object called app
app = FastAPI(title=settings.app_name, description="Daily Bible reading reminders and passages")

# One JSON log line for every request
configure_logging()
app.middleware("http")(log_requests)

app.include_router(events.router)
app.include_router(plans.router)
app.include_router(readings.router)
app.include_router(today.router)
app.include_router(translations.router)
app.include_router(users.router)


# Define the "health" endpoint
@app.get("/health")
def health():
    return {"status": "ok", "app": "Morning Manna", "environment": settings.environment}
