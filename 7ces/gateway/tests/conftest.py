"""Test bootstrap: make gateway modules importable and keep all state in-memory."""
import os
import sys

# Use an in-memory ledger at import time so tests never write a real ledger file.
os.environ.setdefault("LEDGER_PATH", ":memory:")
# Don't let a developer's real keys/caps leak into deterministic tests.
os.environ.setdefault("CAP_PER_REQUEST_USD", "0.50")
os.environ.setdefault("CAP_PER_SESSION_USD", "2.00")
os.environ.setdefault("CAP_PER_DAY_USD", "5.00")

# Put the gateway dir (parent of tests/) on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
