import os

# pydantic-ai prints an observability banner when an agent is built; tests have no terminal.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
