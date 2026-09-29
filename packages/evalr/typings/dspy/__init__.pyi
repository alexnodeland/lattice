"""Minimal type stubs for the parts of DSPy that evalr uses (DSPy ships no type information)."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, ClassVar, Literal, Self

from pydantic.fields import FieldInfo

__version__: str

class Signature:
    instructions: ClassVar[str]
    input_fields: ClassVar[dict[str, FieldInfo]]
    output_fields: ClassVar[dict[str, FieldInfo]]
    fields: ClassVar[dict[str, FieldInfo]]
    @classmethod
    def with_instructions(cls, instructions: str) -> type[Signature]: ...

def make_signature(
    signature: dict[str, tuple[object, FieldInfo]],
    instructions: str | None = None,
    signature_name: str = "StringSignature",
) -> type[Signature]: ...
def InputField(*, desc: str = ...) -> FieldInfo: ...
def OutputField(*, desc: str = ...) -> FieldInfo: ...

class Example:
    def __init__(self, base: Example | dict[str, Any] | None = None, **kwargs: Any) -> None: ...
    def with_inputs(self, *keys: str) -> Self: ...
    def inputs(self) -> Example: ...
    def labels(self) -> Example: ...
    def toDict(self) -> dict[str, Any]: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def keys(self) -> list[str]: ...
    def __getitem__(self, key: str) -> Any: ...

class Prediction(Example):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def get_lm_usage(self) -> dict[str, dict[str, Any]] | None: ...

class BaseLM:
    model: str
    history: list[dict[str, Any]]

class LM(BaseLM):
    def __init__(self, model: str, **kwargs: Any) -> None: ...

class DspyGEPAResult:
    val_aggregate_scores: list[float]
    best_idx: int
    total_metric_calls: int | None

class Module:
    # Set by GEPA.compile(track_stats=True) on the program it returns.
    detailed_results: DspyGEPAResult
    def __call__(self, *args: Any, **kwargs: Any) -> Prediction: ...
    async def acall(self, *args: Any, **kwargs: Any) -> Prediction: ...
    def named_predictors(self) -> list[tuple[str, Predict]]: ...
    def dump_state(self, json_mode: bool = True) -> dict[str, Any]: ...
    def load_state(self, state: dict[str, Any], *, allow_unsafe_lm_state: bool = False) -> Self: ...
    def deepcopy(self) -> Self: ...

class Predict(Module):
    signature: type[Signature]
    def __init__(self, signature: str | type[Signature], **config: Any) -> None: ...

class ChainOfThought(Module):
    predict: Predict
    def __init__(self, signature: str | type[Signature], **config: Any) -> None: ...

def context(**kwargs: Any) -> AbstractContextManager[None]: ...

class GEPA:
    def __init__(
        self,
        metric: Callable[[Example, Prediction, Any, str | None, Any], float | Prediction],
        *,
        auto: Literal["light", "medium", "heavy"] | None = None,
        max_full_evals: int | None = None,
        max_metric_calls: int | None = None,
        reflection_minibatch_size: int = 3,
        candidate_selection_strategy: Literal["pareto", "current_best"] = "pareto",
        reflection_lm: BaseLM | None = None,
        use_merge: bool = True,
        num_threads: int | None = None,
        track_stats: bool = False,
        seed: int | None = 0,
    ) -> None: ...
    def compile(
        self,
        student: Module,
        *,
        trainset: list[Example],
        valset: list[Example] | None = None,
    ) -> Module: ...
