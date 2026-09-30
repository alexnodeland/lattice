"""A fake of TypeSafe's System One API, on the SDK's own transport: no network."""

import json
from typing import Any

import httpx2
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

type Answers = dict[str, dict[str, Any]]


class FakeJev:
    """Answers each question from a script.

    ``script`` maps a text that the state (the rendered input) contains to that input's answers;
    the empty text matches every input. Answers are per field: ``{"noul": 0.7}`` for a yes-or-no
    (or scaled number) question, and ``{"choice": "4", "confidence": 0.8}`` for a choice, whose
    probabilities are filled in. A field with no answer gets the first choice at 0.5, or a noul
    of 0.5.
    """

    def __init__(self, script: dict[str, Answers], *, status: int = 200) -> None:
        self.script = script
        self.status = status
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        body: dict[str, Any] = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            return httpx2.Response(self.status, json={"error": {"message": "unavailable"}})
        state = json.dumps(body["state"])
        scripted: Answers = {}
        for key, answers in self.script.items():
            if key in state:
                scripted = {**scripted, **answers}
        answers = {name: _answer(q, scripted.get(name)) for name, q in body["questions"].items()}
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": answers,
                "usage": {"input_tokens": 1000, "output_tokens": 3},
            },
        )

    def model(self) -> TypeSafeModel:
        client = AsyncTypeSafeClient(
            api_key="test",
            transport=httpx2.MockTransport(self.handler),
            retry=RetryPolicy(max_retries=0),
        )
        return TypeSafeModel("jev-latest", provider=TypeSafeProvider(typesafe_client=client))


def _answer(question: dict[str, Any], scripted: dict[str, Any] | None) -> dict[str, Any]:
    if question["type"] == "noul":
        return {"type": "noul", "noul": (scripted or {}).get("noul", 0.5)}
    labels = list(question["criteria"])
    choice = (scripted or {}).get("choice", labels[0])
    confidence = (scripted or {}).get("confidence", 0.5)
    rest = (1 - confidence) / (len(labels) - 1)
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {label: confidence if label == choice else rest for label in labels},
    }
