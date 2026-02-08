from app.main import app as fastapi_app

# Vercel Python runtime expects an ASGI app named "app".
app = fastapi_app
