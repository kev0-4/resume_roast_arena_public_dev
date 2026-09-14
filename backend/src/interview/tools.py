"""
backend/src/interview/tools.py

The two things the interviewer is allowed to DO, as opposed to say.

Both exist because a v1 review found the interviewer had judgement but no
authority: it correctly identified a candidate wasting its time and told
them so, but had no way to actually end the session -- so six minutes of
paid Live audio ran on regardless. And when a candidate genuinely couldn't
answer, it stonewalled them, because the instruction to press harder on
vague answers had no escape hatch.

Declared in ONE place because the same declarations have to go to two
places that must not drift: locked into the ephemeral token's
live_connect_constraints (which is authoritative -- see llm_client) and
handed to the browser to put in its own connect config.

Shape note: snake_case `function_declarations` is used rather than the
JS SDK's camelCase `functionDeclarations`. Verified against the real API
that the JS SDK accepts this form and the model calls the tool, so one
definition serves both sides instead of two that can disagree.
"""

END_INTERVIEW = "end_interview"
SKIP_QUESTION = "skip_question"

# Kept as an enum so scoring gets a reliable category rather than having to
# parse intent back out of a free-text reason.
END_CATEGORIES = ("COMPLETE", "TIME_WASTING", "CANDIDATE_DISENGAGED")

INTERVIEW_TOOLS = [
    {
        "function_declarations": [
            {
                "name": END_INTERVIEW,
                "description": (
                    "End the interview now and send the candidate to scoring. Call this when you "
                    "have genuinely covered enough ground, or when the candidate is wasting your "
                    "time and has not corrected course after one warning. Say your closing line "
                    "BEFORE calling this."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "reason": {
                            "type": "STRING",
                            "description": "One short sentence on why the interview is ending. The candidate may see this.",
                        },
                        "category": {
                            "type": "STRING",
                            "enum": list(END_CATEGORIES),
                            "description": (
                                "COMPLETE if the interview ran its course. TIME_WASTING if the candidate "
                                "was deliberately burning time. CANDIDATE_DISENGAGED if they stopped "
                                "participating in good faith."
                            ),
                        },
                    },
                    "required": ["reason", "category"],
                },
            },
            {
                "name": SKIP_QUESTION,
                "description": (
                    "Move on from the current question because the candidate cannot or will not "
                    "answer it. Call this only AFTER you have pushed back once and they still "
                    "decline. Calling this is recorded and counts against their score, so do not "
                    "call it merely because an answer was weak -- only when they actually decline."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "question": {
                            "type": "STRING",
                            "description": "The question being skipped, in a few words.",
                        },
                    },
                    "required": ["question"],
                },
            },
        ]
    }
]
