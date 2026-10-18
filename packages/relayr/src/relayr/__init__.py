"""relayr: the bridge between artifactr and reflexr.

Events from chats and artifacts become events for rules, and runs act back in the chat as
proposals and notices. relayr uses only the two libraries' public APIs, and neither library
imports it or the other.

Its adapters are built: [`relayr.events`][relayr.events], the bridged types and the projections;
[`relayr.ledger`][relayr.ledger] and [`relayr.sql`][relayr.sql], its storage;
[`relayr.inbound`][relayr.inbound], the followers; [`relayr.outbound`][relayr.outbound], what
rules' runs do in artifactr; [`relayr.trackers`][relayr.trackers], with `relayr.plane`,
`relayr.vikunja` and [`relayr.fastapi`][relayr.fastapi], the connector to task trackers, both
ways; and [`relayr.telemetry`][relayr.telemetry], with
[`relayr.otel`][relayr.otel] and [`relayr.langfuse`][relayr.langfuse], their traces, tags and
counters. Its documentation, with its decisions and the
plan that builds the rest, is at <https://lattice.alexnodeland.com/relayr/>.
"""

from importlib.metadata import version

__version__ = version("relayr-ai")

__all__ = ["__version__"]
