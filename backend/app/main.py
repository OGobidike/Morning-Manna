

# import the FastAPI class from the fastapi module
from fastapi import FastAPI

# creates application object called app
app = FastAPI()

# Define the "health" endpoint
@app.get("/health")
def health():
    return {"status": "ok", "app": "Morning Manna", "version": "1.0.0"}
