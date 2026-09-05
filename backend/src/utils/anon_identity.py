"""
backend/src/utils/anon_identity.py

Generates fun, Reddit/Kahoot-style display names and a unique firebase_uid
placeholder for anonymous (unauthenticated) roast sessions.
"""

import secrets
import uuid

_ADJECTIVES = [
    "Savage", "Brutal", "Cynical", "Awkward", "Feral", "Salty", "Chaotic",
    "Ruthless", "Sleepy", "Jaded", "Reckless", "Sarcastic", "Grumpy",
    "Unhinged", "Shady", "Blunt", "Nervous", "Overqualified", "Underpaid",
    "Caffeinated", "Burned-out", "Overconfident", "Anxious", "Stoic",
    "Feisty", "Rogue", "Cursed", "Weary", "Petty", "Spicy",
]

_NOUNS = [
    "Intern", "Recruiter", "Freelancer", "Founder", "Manager", "Analyst",
    "Engineer", "Consultant", "Graduate", "Applicant", "Barista", "Coder",
    "Wizard", "Ninja", "Rockstar", "Guru", "Hustler", "Grinder", "Raccoon",
    "Goblin", "Otter", "Falcon", "Wolf", "Badger", "Crow", "Panda",
    "Toaster", "Robot", "Gremlin", "Phoenix",
]


def generate_anon_display_name() -> str:
    """e.g. 'SavageIntern4821' -- friendly, never offensive, not unique."""
    adjective = secrets.choice(_ADJECTIVES)
    noun = secrets.choice(_NOUNS)
    number = secrets.randbelow(9000) + 1000
    return f"{adjective}{noun}{number}"


def generate_anon_firebase_uid() -> str:
    """Unique placeholder used as Users.firebase_uid for anonymous sessions."""
    return f"anon:{uuid.uuid4()}"
