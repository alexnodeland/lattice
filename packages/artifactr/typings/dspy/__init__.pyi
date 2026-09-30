"""Minimal type stubs for the parts of DSPy docplan uses, itself or through evalr's DspyJudge.

DSPy ships no type information.
"""

from typing import Any

class BaseLM:
    model: str

class LM(BaseLM):
    def __init__(self, model: str, **kwargs: Any) -> None: ...
