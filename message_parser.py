"""
Message parser module for detecting temperature-related requests.
"""

from enum import Enum
import re


class TemperatureAction(Enum):
    INCREASE = "increase"  # Too cold, need to warm up
    DECREASE = "decrease"  # Too hot, need to cool down
    NONE = "none"


# Keywords indicating it's too cold (need to increase temperature / reduce AC)
COLD_KEYWORDS = [
    r"\bcold\b",
    r"\bfreezing\b",
    r"\bchilly\b",
    r"\bcool\b",
    r"\bshivering\b",
    r"too\s+cold",
    r"very\s+cold",
    r"increase\s+(the\s+)?temp",
    r"turn\s+(up|on)\s+(the\s+)?(heat|ac|temperature)",
    r"raise\s+(the\s+)?temp",
    r"warmer",
    r"warm\s+it\s+up",
]

# Keywords indicating it's too hot (need to decrease temperature / increase AC)
HOT_KEYWORDS = [
    r"\bhot\b",
    r"\bwarm\b",
    r"\bsweating\b",
    r"\bstuffy\b",
    r"\bboiling\b",
    r"too\s+hot",
    r"very\s+hot",
    r"too\s+warm",
    r"decrease\s+(the\s+)?temp",
    r"reduce\s+(the\s+)?temp",
    r"turn\s+(up|on)\s+(the\s+)?(ac|air\s*con)",
    r"turn\s+down\s+(the\s+)?(heat|temperature)",
    r"lower\s+(the\s+)?temp",
    r"cooler",
    r"cool\s+it\s+down",
]


def parse_temperature_request(message: str) -> TemperatureAction:
    """
    Analyze a message to determine if it's a temperature change request.

    Args:
        message: The message text to analyze

    Returns:
        TemperatureAction indicating what action to take
    """
    message_lower = message.lower()

    # Check for cold-related keywords (need to increase temp)
    for pattern in COLD_KEYWORDS:
        if re.search(pattern, message_lower):
            return TemperatureAction.INCREASE

    # Check for hot-related keywords (need to decrease temp)
    for pattern in HOT_KEYWORDS:
        if re.search(pattern, message_lower):
            return TemperatureAction.DECREASE

    return TemperatureAction.NONE


def get_action_description(action: TemperatureAction) -> str:
    """Get a human-readable description of the action."""
    if action == TemperatureAction.INCREASE:
        return "increase the temperature (it's too cold)"
    elif action == TemperatureAction.DECREASE:
        return "decrease the temperature (it's too hot)"
    return "no temperature change needed"
