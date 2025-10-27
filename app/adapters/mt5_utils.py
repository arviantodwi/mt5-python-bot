from typing import Tuple

import mt5_wrapper as mt5


def parse_mt5_version(version: Tuple[int, int, str]) -> str:
    release, build, date = version

    major = release // 100
    minor = release % 100
    release = f"{major}.{minor:02d}"

    return f"{release} build {build} ({date})"


def with_mt5_error(prefix: str) -> str:
    if (error := mt5.last_error()) is None:
        return prefix

    code, message = error
    return f"{prefix} ({code}: {message})"
