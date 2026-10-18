"""The people and agents the tests act as."""

from artifactr.core import AgentActor, UserActor

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")
ADMIN = UserActor(id="admin", name="An admin")


def agent(
    thread_id: str, *, run_id: str = "run_1", acting_for: UserActor | None = ALICE
) -> AgentActor:
    """A thread's agent in one run, acting for a person, or for no one."""
    return AgentActor(thread_id=thread_id, run_id=run_id, on_behalf_of=acting_for)
