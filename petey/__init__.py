"""Petey package bootstrap."""

from pathlib import Path

from dotenv import load_dotenv


# Load the project environment before provider singletons are constructed.
# Explicit process environment variables retain precedence over `.env` values.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
