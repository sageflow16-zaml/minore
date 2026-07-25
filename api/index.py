import sys
import os
from pathlib import Path

# Set Vercel environment flag
os.environ["VERCEL"] = "1"

# Get the backend directory path (parent of api, then into backend)
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(backend_path / "src"))

# Import settings and configure environment
from src.core.config import settings

# Validate JWT_SECRET_KEY for production
if settings.ENVIRONMENT == "production" and settings.JWT_SECRET_KEY in (
    "change-me-in-production",
    "change-me-to-a-random-secret-at-least-32-chars-long",
    "",
):
    import logging
    logging.warning(
        "JWT_SECRET_KEY is set to a weak/default value. "
        "Generate a secure key with: openssl rand -hex 32"
    )

# Register all agents
from src.agents.factory import register_all_agents
register_all_agents()

# Import the FastAPI app
from src.main import app

# Vercel serverless handler
handler = app
