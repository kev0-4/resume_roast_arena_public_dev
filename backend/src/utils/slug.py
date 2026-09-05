"""
backend/src/utils/slug.py

Generates short public slugs for shareable roast card links (GET /r/<slug>).
"""

import secrets

# Unambiguous alphabet -- no 0/o, 1/l/i confusion when read/typed by hand.
_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
_SLUG_LENGTH = 8


def generate_slug() -> str:
    """8 chars from a 32-symbol unambiguous alphabet (~40 bits of entropy)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_SLUG_LENGTH))
