import os
import sys
from typing import Literal, Optional, Tuple, cast

import mt5_wrapper as mt5
import numpy as np
from colorama import Fore, Style

message_tag_list = ["FATAL", "ERROR", "WARN", "INFO", "OK", "DEBUG", "AWAIT"]
type MessageTag = Literal["FATAL", "ERROR", "WARN", "INFO", "OK", "DEBUG", "AWAIT"]


def with_mt5_error(message: str, tag: MessageTag = "ERROR") -> str:
    if (error := mt5.last_error()) is not None:
        mt5_error_code, mt5_error_message = error
        message = f"{message} {mt5_error_code}: {mt5_error_message}"

    return f"{with_tag(message, tag)}"


def with_tag(message: str, tag: MessageTag = "INFO") -> str:
    return f"{stylize_tag(tag)} {message}"


def stylize_tag(tag: MessageTag) -> str:
    right_padded_tag = tag
    max_available_tag_length = len(max(message_tag_list, key=len))
    arg_tag_length = len(tag)
    diff = max_available_tag_length - arg_tag_length
    if diff > 0:
        right_padded_tag = f"{tag}{' ' * diff}"

    return f"{colorize_text(f'[{right_padded_tag}]', tag)}"


def colorize_text(text: str, type: MessageTag = "INFO"):
    color = None
    match type:
        case "FATAL":
            color = Fore.RED
        case "ERROR":
            color = Fore.MAGENTA
        case type if type == "WARN" or type == "AWAIT":
            color = Fore.YELLOW
        case "INFO":
            color = Fore.CYAN
        case "OK":
            color = Fore.GREEN
        case _:
            pass

    return f"{color}{text}{Style.RESET_ALL}" if color is not None else text


def clear_and_print(message: str, end: Optional[str] = "\n", flush: Optional[bool] = True) -> None:
    """
    Clears the current terminal line by overwriting it with spaces,
    moves the cursor back, and then prints the new message.

    This uses sys.stdout.write for reliable line manipulation.

    Args:
        message (str): The string to print.
        end (Optional[str]): The string appended after the last value, default is newline.
        flush (bool): Whether to forcibly flush the stream, default is True for immediate output.
    """

    terminal_width = 80
    try:
        # Get actual terminal size
        terminal_width = os.get_terminal_size().columns
    except Exception:
        pass

    stdout_strings = (
        "\r" + " " * terminal_width,
        "\r",
        message + cast(str, end),
    )

    for i in range(3):
        sys.stdout.write(stdout_strings[i])
        if flush:
            sys.stdout.flush()


def parse_mt5_version(version: Tuple[int, int, str]) -> str:
    release, build, date = version

    major = release // 100
    minor = release % 100
    release = f"{major}.{minor:02d}"

    return f"{release} build {build} ({date})"


def to_percent_string(number: int | float):
    return str("{}%".format(to_decimals(number, 2)))


def to_decimals(number: int | float, decimals: int) -> float:
    decimal_scale = 10**decimals
    return np.ceil(number * decimal_scale) / decimal_scale
