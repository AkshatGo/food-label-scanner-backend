import os
from pathlib import Path

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient


# Load the backend environment file regardless of the process working directory.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv(
    "DATABASE_NAME",
    "food_label_scanner"
)


if not MONGODB_URI:
    raise RuntimeError(
        "MONGODB_URI is missing from .env"
    )


# MongoDB Atlas connection
client = MongoClient(
    MONGODB_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000
)


# Select database
db = client[DATABASE_NAME]


# Select scans collection
scans_collection = db["scans"]


def test_connection():
    """Ping MongoDB Atlas and return the server response."""
    client.admin.command("ping")
    return True