import sys
import os

# Make the project root importable so workers.* and backend.* resolve correctly
_root = os.path.dirname(__file__)
sys.path.insert(0, _root)
# backend/src/__init__.py does `from src.routes... import ...` (absolute, not
# relative) -- backend/ must also be on sys.path for that "src" to resolve,
# same as every manual script in this repo already has to do.
sys.path.insert(0, os.path.join(_root, "backend"))

# backend/src/config.py and backend/src/db/session.py both call load_dotenv()
# with no path, which searches upward from the CWD -- when pytest runs from
# the repo root that never finds workers/.env, so DATABASE_URL etc. end up
# unset and any test importing backend.src.* fails at import time. Load it
# explicitly, before anything else imports backend.src.
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, "workers", ".env"), override=True)
