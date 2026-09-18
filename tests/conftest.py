"""Shared pytest fixtures."""

import os

# Force in-memory storage for the whole test session (no MongoDB dependency).
# Assignment, not setdefault: a real MONGODB_URI leaking into the environment
# must never silently redirect tests at live data.
os.environ["MONGODB_URI"] = ""
os.environ["JWT_SECRET"] = "test-secret-not-for-production-0123456789abcdef"
