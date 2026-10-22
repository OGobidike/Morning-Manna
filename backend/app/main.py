

# import the FastAPI class from the fastapi module
from fastapi import FastAPI

from app.config import settings
from app.routers import plans, readings, today, users

# creates application object called app
app = FastAPI(title=settings.app_name, description="Daily Bible reading reminders and passages")
app.include_router(plans.router)
app.include_router(readings.router)
app.include_router(today.router)
app.include_router(users.router)


# Define the "health" endpoint
@app.get("/health")
def health():
    return {"status": "ok", "app": "Morning Manna", "environment": settings.environment}
