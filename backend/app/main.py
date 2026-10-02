

# import the FastAPI class from the fastapi module
from fastapi import FastAPI

from app.config import settings

# creates application object called app
app = FastAPI(title=settings.app_name, description="Daily Bible reading reminders and passages")


# Define the "health" endpoint
@app.get("/health")
def health():
    return {"status": "ok", "app": "Morning Manna", "environment": settings.environment}
