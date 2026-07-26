"""
Vercel Python Serverless Function Entry Point

This module serves as the entry point for Vercel serverless deployment.
The api/ directory is the default location for Vercel Python functions.
"""
import sys
import os
from pathlib import Path

# Set Vercel environment flag
os.environ["VERCEL"] = "1"

# Calculate paths relative to this file (api/index.py at repo root)
current_dir = Path(__file__).resolve().parent  # api/
repo_root = current_dir.parent  # repo root
backend_dir = repo_root / "backend"
src_path = backend_dir / "src"

# Add backend/ to Python path (so 'src' module can be imported)
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Set APP_VERSION environment variable from backend/VERSION if available
version_file = backend_dir / "VERSION"
if version_file.exists() and "APP_VERSION" not in os.environ:
    os.environ["APP_VERSION"] = version_file.read_text().strip()

# Import the FastAPI application
from src.main import app

# Vercel requires the app to be exported as a handler
handler = app
