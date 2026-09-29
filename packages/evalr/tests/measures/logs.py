"""What the libraries' [evals] extras do: put their recorded logs into evalr's measure inputs.

The fixtures are recorded in each library's log shape (artifactr's envelopes of thread, artifact
and proposal events; reflexr's envelopes of events in causal chains), and read here without
importing either library.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from evalr.measures import Activity, History, Revision, Role, Session, Transcript, Turn

FIXTURES = Path(__file__).parent / "fixtures"

ROLES: dict[str, Role] = {"user": "person", "agent": "agent"}


def recorded(library: str) -> tuple[datetime, list[dict[str, Any]]]:
    log = json.loads((FIXTURES / f"{library}.json").read_text())
    return datetime.fromisoformat(log["recorded_until"]), log["events"]


def role(actor: dict[str, Any]) -> Role:
    return ROLES.get(actor["kind"], "system")


# ─── artifactr ────────────────────────────────────────────────────────────────


def artifactr_sessions(events: list[dict[str, Any]]) -> list[Session]:
    kinds = {"proposal_created": "proposal", "proposal_resolved": "resolution"}
    threads: dict[str, list[Activity]] = defaultdict(list)
    for envelope in events:
        event = envelope["event"]
        kind: str = kinds.get(event["type"]) or event["type"]
        threads[envelope["thread_id"]].append(
            Activity(
                at=datetime.fromisoformat(envelope["ts"]),
                role=role(envelope["actor"]),
                kind=kind,
                ref=event.get("proposal_id"),
            )
        )
    return [Session(id=thread, activities=activities) for thread, activities in threads.items()]


def artifactr_histories(events: list[dict[str, Any]]) -> list[History]:
    artifacts: dict[str, list[Revision]] = defaultdict(list)
    for envelope in events:
        event = envelope["event"]
        if event["type"] == "artifact_created":
            text = event["data"]["text"]
        elif event["type"] == "artifact_changed":
            (operation,) = event["patch"]
            text = operation["value"]
        else:
            continue
        artifacts[event["artifact_id"]].append(
            Revision(
                at=datetime.fromisoformat(envelope["ts"]), role=role(envelope["actor"]), text=text
            )
        )
    return [History(id=artifact, revisions=revisions) for artifact, revisions in artifacts.items()]


def artifactr_transcripts(events: list[dict[str, Any]]) -> dict[str, Transcript]:
    turns: dict[str, list[Turn]] = defaultdict(list)
    results: dict[str, str] = {}
    for history in artifactr_histories(events):
        thread = next(e["thread_id"] for e in events if e["event"].get("artifact_id") == history.id)
        results[thread] = history.revisions[-1].text
    for envelope in events:
        if envelope["event"]["type"] == "message_posted":
            turns[envelope["thread_id"]].append(
                Turn(role=role(envelope["actor"]), text=envelope["event"]["content"])
            )
    return {
        thread: Transcript(request=said[0].text, turns=said, result=results.get(thread))
        for thread, said in turns.items()
    }


# ─── reflexr ──────────────────────────────────────────────────────────────────


def reflexr_sessions(events: list[dict[str, Any]]) -> list[Session]:
    chains: dict[str, list[Activity]] = defaultdict(list)
    for envelope in events:
        kind: str = envelope["event"]["type"]
        if kind.endswith(".proposed"):
            kind = "proposal"
        elif kind.endswith((".approved", ".rejected")):
            kind = "resolution"
        chains[envelope["correlation_id"]].append(
            Activity(
                at=datetime.fromisoformat(envelope["ts"]),
                role=role(envelope["actor"]),
                kind=kind,
                ref=envelope["event"].get("proposal_id"),
            )
        )
    return [Session(id=chain, activities=activities) for chain, activities in chains.items()]


def reflexr_transcripts(events: list[dict[str, Any]]) -> dict[str, Transcript]:
    chains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for envelope in events:
        chains[envelope["correlation_id"]].append(envelope)
    transcripts: dict[str, Transcript] = {}
    for chain, envelopes in chains.items():
        first = envelopes[0]["event"]
        said = [
            Turn(
                role=role(e["actor"]),
                text=e["event"].get("summary") or e["event"].get("note") or e["event"]["type"],
            )
            for e in envelopes
            if role(e["actor"]) != "system"
        ]
        transcripts[chain] = Transcript(
            request=f"Handle the {first['service']} error of severity {first['severity']}",
            turns=said,
        )
    return transcripts
