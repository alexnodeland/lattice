"""Why grantr refuses a command that changes access."""


class GrantrError(Exception):
    """A command grantr refused. Checks never raise: they answer ``False``."""


class Forbidden(GrantrError):
    """The actor may not do this: it lacks the action, or holds less than it would give."""


class Invalid(GrantrError):
    """The command can't apply: an unknown tenant, role, group or key, or a duplicate."""
