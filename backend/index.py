"""
Vercel Python Handler for Project Minore Backend

This module serves as the entry point for Vercel serverless deployment.
"""
import sys
import os
from pathlib import Path

# Set Vercel environment flag
os.environ["VERCEL"] = "1"

# Ensure the backend/src directory is in the Python path
# This allows imports like "from src.main import app"
current_dir = Path(__file__).resolve().parent
src_path = current_dir / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Create a VERSION file in the backend directory if it doesn't exist
# This is needed because main.py reads VERSION from project root
version_file = current_dir / "VERSION"
if not version_file.exists():
    # Try to copy from parent (repo root) if it exists
    parent_version = current_dir.parent / "VERSION"
    if parent_version.exists():
        version_file.write_text(parent_version.read_text())

# Import the FastAPI application
from src.main import app

# Vercel serverless handler
handler = app
