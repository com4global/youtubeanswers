from fastapi import FastAPI
from app.main import app as fastapi_app

# Vercel Python runtime expects an ASGI app named "app".
# Mount the FastAPI app under /api so routes match /api/*.
app = FastAPI()
app.mount("/api", fastapi_app)
