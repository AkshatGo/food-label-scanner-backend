"""Shared pytest fixtures."""

import os

# Force in-memory storage for the whole test session (no MongoDB dependency).
os.environ.setdefault("MONGODB_URI", "")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")
