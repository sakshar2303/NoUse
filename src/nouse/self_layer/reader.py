from __future__ import annotations

from pathlib import Path
from typing import Any

from nouse.self_layer.living_core import LIVING_CORE_PATH, identity_prompt_fragment, load_living_core


def read_self_state(path: Path = LIVING_CORE_PATH) -> dict[str, Any]:
    return load_living_core(path)


def read_identity_prompt(path: Path = LIVING_CORE_PATH) -> str:
    return identity_prompt_fragment(load_living_core(path))
