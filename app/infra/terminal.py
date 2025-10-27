import os


def clear_terminal():
    """Clear the terminal screen on Windows, Unix, and Linux."""
    if os.name == "nt":  # Windows
        _ = os.system("cls")
    else:  # Unix and Linux
        _ = os.system("clear")
