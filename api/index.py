"""Vercel serverless function adapter for the FastAPI app."""

from vercel_asgi import VercelASGI
from app import app

# Wrap the FastAPI app with Vercel ASGI adapter
handler = VercelASGI(app)