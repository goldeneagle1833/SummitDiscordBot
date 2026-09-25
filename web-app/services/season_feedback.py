"""Post-season feedback survey: question schema and answer validation.

The schema here is the single source of truth. The public form renders from
it, submissions are validated against it, and the admin CSV export uses its
question order for columns. To run a new survey, change CURRENT_SEASON and
edit the questions below; old responses keep their season label.

Question types:
    scale     - integer from ``min`` to ``max``; ``labels`` names the endpoints.
                ``allow_na`` lets the player pick "N/A", stored as null.
    radio     - one of ``options``.
    select    - one of ``options`` (rendered as a dropdown).
    checkbox  - list drawn from ``options``; ``allow_other`` accepts one
                free-text entry prefixed with "Other: ".
    text      - short free text.
    textarea  - long free text.

``show_if`` hides a question until another answer matches one of the listed
values. Hidden questions are stored as null even if the player answered them
before changing the controlling answer.
"""

from __future__ import annotations

CURRENT_SEASON = "Gothic Summit Season 7"

SHORT_TEXT_MAX = 200
LONG_TEXT_MAX = 2000
OTHER_PREFIX = "Other: "

FIRST_SEASON = {"key": "seasons_played", "values": ["This is my first"]}
HAD_ISSUE = {"key": "negative_interactions", "values": ["Yes, minor", "Yes, serious"]}

# Kept short on purpose: about two minutes, mostly taps, three text boxes.
SECTIONS: list[dict] = [
    {
        "title": "About you",
        "questions": [
            {
                "key": "seasons_played",
                "label": "How many Summit seasons have you played?",
                "type": "radio",
                "options": ["This is my first", "2-3", "4+"],
                "required": True,
            },
        ],
    },
    {
        "title": "New players",
        "questions": [
            {
                "key": "welcome_rating",
                "label": "How welcome did you feel as a new player?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": ["Not welcome", "Very welcome"],
                "show_if": FIRST_SEASON,
            },
            {
                "key": "hardest_to_learn",
                "label": "What was hardest to figure out when you started?",
                "type": "checkbox",
                "options": [
                    "Joining the queue", "Reporting results",
                    "Sorcery Online tables", "Voice rules", "How ELO works",
                    "Finding games at my times",
                ],
                "allow_other": True,
                "show_if": FIRST_SEASON,
            },
        ],
    },
    {
        "title": "Games and voice",
        "questions": [
            {
                "key": "match_balance",
                "label": "How balanced did your matches feel?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": ["Very one-sided", "Very even"],
            },
            {
                "key": "voice_mode",
                "label": "Did you play mostly with voice or without?",
                "type": "radio",
                "options": ["Mostly voice", "Mostly no voice", "A mix"],
            },
            {
                "key": "voice_rule",
                "label": "What should the voice rule be going forward?",
                "type": "radio",
                "options": [
                    "Required", "Encouraged but optional",
                    "Opponents agree before each game", "No preference",
                ],
            },
            {
                "key": "voice_thoughts",
                "label": "How did games with and without voice feel?",
                "hint": "Anything you liked, disliked, or found awkward.",
                "type": "textarea",
            },
        ],
    },
    {
        "title": "Sportsmanship",
        "questions": [
            {
                "key": "negative_interactions",
                "label": "Did you have any negative interactions this season?",
                "type": "radio",
                "options": ["No", "Yes, minor", "Yes, serious"],
            },
            {
                "key": "negative_detail",
                "label": "What happened?",
                "hint": (
                    "Only the organizers see this. For anything serious, "
                    "please also message a mod directly."
                ),
                "type": "textarea",
                "show_if": HAD_ISSUE,
            },
        ],
    },
    {
        "title": "Bot and ELO",
        "questions": [
            {
                "key": "bot_ease",
                "label": "How easy was the Summit bot to use?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": ["Very difficult", "Very easy"],
            },
            {
                "key": "elo_rating",
                "label": "How much did you like the ELO system?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": ["Disliked it", "Loved it"],
            },
        ],
    },
    {
        "title": "Wrap-up",
        "questions": [
            {
                "key": "enjoyment",
                "label": "Overall, how much did you enjoy the season?",
                "type": "scale",
                "min": 1,
                "max": 10,
                "labels": ["Not enjoyable", "Amazing"],
                "required": True,
            },
            {
                "key": "play_next_season",
                "label": "How likely are you to play next season?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": ["Very unlikely", "Definitely"],
            },
            {
                "key": "improvements",
                "label": "What should we add, change, or fix for next season?",
                "type": "textarea",
            },
            {
                "key": "discord_name",
                "label": "Discord name (optional)",
                "hint": "Only used if we need to follow up on something you wrote.",
                "type": "text",
            },
        ],
    },
]

QUESTIONS: list[dict] = [q for section in SECTIONS for q in section["questions"]]
QUESTIONS_BY_KEY: dict[str, dict] = {q["key"]: q for q in QUESTIONS}


def get_form() -> dict:
    """Schema the public form renders from."""
    return {"season": CURRENT_SEASON, "sections": SECTIONS}


def _is_shown(question: dict, answers: dict) -> bool:
    cond = question.get("show_if")
    if not cond:
        return True
    return answers.get(cond["key"]) in cond["values"]


def _clean_text(value, limit: int, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"{key} must be {limit} characters or less")
    return value


def _clean_scale(value, question: dict) -> int | None:
    key = question["key"]
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{key} must be a number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number") from None
    if not question["min"] <= number <= question["max"]:
        raise ValueError(
            f"{key} must be between {question['min']} and {question['max']}"
        )
    return number


def _clean_choice(value, question: dict) -> str | None:
    key = question["key"]
    if value is None or value == "":
        return None
    if value not in question["options"]:
        raise ValueError(f"{key} has an invalid choice")
    return value


def _clean_checkbox(value, question: dict) -> list[str] | None:
    key = question["key"]
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    chosen: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} has an invalid choice")
        if item in question["options"]:
            if item not in chosen:
                chosen.append(item)
        elif question.get("allow_other") and item.startswith(OTHER_PREFIX):
            other = _clean_text(item[len(OTHER_PREFIX):], SHORT_TEXT_MAX, key)
            if other:
                chosen.append(OTHER_PREFIX + other)
        else:
            raise ValueError(f"{key} has an invalid choice")
    return chosen or None


def validate_answers(raw: dict) -> dict:
    """Return a cleaned answer dict keyed by every question in the schema.

    Unknown keys are dropped, hidden questions are nulled, and a ValueError
    names the first problem found so the form can show it.
    """
    if not isinstance(raw, dict):
        raise ValueError("answers must be an object")

    cleaned: dict = {}
    for question in QUESTIONS:
        key = question["key"]
        value = raw.get(key)
        kind = question["type"]
        if kind == "scale":
            cleaned[key] = _clean_scale(value, question)
        elif kind in ("radio", "select"):
            cleaned[key] = _clean_choice(value, question)
        elif kind == "checkbox":
            cleaned[key] = _clean_checkbox(value, question)
        elif kind == "text":
            cleaned[key] = _clean_text(value, SHORT_TEXT_MAX, key)
        elif kind == "textarea":
            cleaned[key] = _clean_text(value, LONG_TEXT_MAX, key)
        else:  # pragma: no cover - schema error
            raise ValueError(f"unknown question type {kind}")

    # Conditional questions only count when their trigger is chosen.
    for question in QUESTIONS:
        if not _is_shown(question, cleaned):
            cleaned[question["key"]] = None

    for question in QUESTIONS:
        if question.get("required") and cleaned.get(question["key"]) is None:
            raise ValueError(f"Please answer: {question['label']}")

    return cleaned


def summarize(responses: list[dict]) -> dict:
    """Per-question tallies for the admin view.

    Scale questions get an average and a count; choice questions get a count
    per option (checkbox "Other" entries are grouped under "Other").
    """
    summary: dict = {}
    for question in QUESTIONS:
        key = question["key"]
        kind = question["type"]
        if kind == "scale":
            values = [
                r["answers"].get(key) for r in responses
                if isinstance(r["answers"].get(key), int)
            ]
            summary[key] = {
                "type": "scale",
                "count": len(values),
                "average": round(sum(values) / len(values), 2) if values else None,
                "min": question["min"],
                "max": question["max"],
            }
        elif kind in ("radio", "select", "checkbox"):
            counts = {option: 0 for option in question["options"]}
            if question.get("allow_other"):
                counts["Other"] = 0
            answered = 0
            for r in responses:
                value = r["answers"].get(key)
                if value is None:
                    continue
                answered += 1
                items = value if isinstance(value, list) else [value]
                for item in items:
                    if item in counts:
                        counts[item] += 1
                    elif isinstance(item, str) and item.startswith(OTHER_PREFIX):
                        counts["Other"] = counts.get("Other", 0) + 1
            summary[key] = {"type": "choice", "count": answered, "counts": counts}
        else:
            answered = sum(1 for r in responses if r["answers"].get(key))
            summary[key] = {"type": "text", "count": answered}
    return summary


def csv_columns() -> list[str]:
    return ["id", "season", "submitted_at", "username", "user_id"] + [
        q["key"] for q in QUESTIONS
    ]


def csv_row(response: dict) -> dict:
    row = {
        "id": response["id"],
        "season": response["season"],
        "submitted_at": response["created_at"],
        "username": response.get("username") or "",
        "user_id": response.get("user_id") or "",
    }
    for question in QUESTIONS:
        value = response["answers"].get(question["key"])
        if value is None:
            row[question["key"]] = ""
        elif isinstance(value, list):
            row[question["key"]] = "; ".join(value)
        else:
            row[question["key"]] = value
    return row
