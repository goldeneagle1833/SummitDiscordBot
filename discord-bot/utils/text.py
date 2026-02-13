"""Shared text utility functions for the Discord bot."""


def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def find_best_command_match(failed_command, command_suggestions, actual_commands, max_distance=3):
    """
    Find the best matching command for a mistyped input.

    Uses a 3-step matching strategy:
    1. Exact match in the alias/suggestion dictionary
    2. Partial/substring match in the alias dictionary
    3. Levenshtein fuzzy match on actual command names

    Args:
        failed_command: The command the user typed (without prefix).
        command_suggestions: Dict mapping aliases/variations -> "!actual_command".
        actual_commands: Dict mapping canonical command names -> "!actual_command".
        max_distance: Maximum Levenshtein distance to consider a match.

    Returns:
        The suggested command string (e.g., "!fart") or None if no match found.
    """
    # 1. Exact match in aliases
    if failed_command in command_suggestions:
        return command_suggestions[failed_command]

    # 2. Partial/substring match
    for key, suggestion in command_suggestions.items():
        if key in failed_command or failed_command in key:
            return suggestion

    # 3. Levenshtein fuzzy match on actual command names
    best_match = None
    min_dist = float("inf")

    for command_name, suggestion in actual_commands.items():
        distance = levenshtein_distance(failed_command, command_name)
        if distance <= max_distance and distance < min_dist:
            if abs(len(failed_command) - len(command_name)) <= max_distance:
                min_dist = distance
                best_match = suggestion

    return best_match
