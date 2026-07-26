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

# Calculate paths relative to this file (api/index.py)
# Backend source is at: <root>/backend/src
# This file is at: <root>/backend/api/index.py
current_dir = Path(__file__).resolve().parent  # api/
backend_dir = current_dir.parent  # backend/
src_path = backend_dir / "src"

# Add backend/src to Python path
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Copy VERSION file to backend directory if it doesn't exist
# (needed by src/main.py to read app version)
version_file = backend_dir / "VERSION"
if not version_file.exists():
    parent_version = backend_dir.parent / "VERSION"
    if parent_version.exists():
        version_file.write_text(parent_version.read_text())

# Import the FastAPI application
from src.main import app

# Vercel requires the app to be exported as a handler
handler = app
