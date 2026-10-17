"""A scripted model, so that no test calls a model API."""

from collections.abc import Callable
from typing import Any

from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from artifactr.agent import function_model

Step = ModelResponse | Callable[[list[ModelMessage]], ModelResponse]


def say(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def call(tool: str, call_id: str = "call_1", **args: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args, tool_call_id=call_id)])


class Script:
    """A model that answers each request with the next step, recording each request."""

    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)
        self.requests: list[list[ModelMessage]] = []
        self.tools: list[list[str]] = []

    @property
    def model(self) -> FunctionModel:
        return function_model(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(list(messages))
        self.tools.append(sorted(tool.name for tool in info.function_tools))
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step

    def last_parts(self, request: int) -> list[Any]:
        """The parts of a request's last message: the tools' returns and retries among them."""
        last = self.requests[request][-1]
        assert isinstance(last, ModelRequest)
        return list(last.parts)

    def calls(self, request: int) -> list[ToolCallPart]:
        """Every tool call the model made before a request, as the request's history holds it."""
        return [
            part
            for message in self.requests[request]
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
