"""
workers/renderer/pipeline/template.py

Renders the roast card HTML from a card_data context dict.
"""

from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)))
_template = _env.get_template("roast_card.html")


def render_html(context: Dict[str, Any]) -> str:
    return _template.render(**context)
