"""Vercel serverless function adapter for the FastAPI app."""

from app import app

# For Vercel deployment, we can export the FastAPI app directly
# Vercel will handle the ASGI interface automatically
handler = app