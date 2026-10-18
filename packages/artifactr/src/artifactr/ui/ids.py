"""A submission's id, derived from what it answers, so a form's policy is artifactr's refusal.

artifactr refuses to create an artifact whose id exists, so a derived id makes a retried submit
one artifact, and a form that takes one submission, or one a person, takes no second
(ADR-0045's pattern, and relayr ADR-0019's). The check in
:mod:`artifactr.ui.checks` recomputes it and refuses a submission whose id isn't its derivation.
portalr derives the same ids, and its tests read the vectors in
``tests/vectors/submission_ids.json``.
"""

import hashlib

__all__ = ["submission_id"]


def submission_id(form_id: str, *, principal: str | None = None, nonce: str | None = None) -> str:
    """Derive a submission's id: ``sub_`` and 32 hex digits of a SHA-256 digest.

    The digest is of the parts joined by a NUL, which no id holds, since artifactr refuses one:
    the policy and the form's id, ``once``, for a form that takes one submission; with the
    person's principal, ``acting_for(actor).participant``, ``per_person``, for one a person; or
    with the nonce the client makes once per submit and keeps in the submission, ``many``. The
    policy is a part, so a form whose policy changes takes submissions afresh, and no nonce
    passes for a principal. A submission to an app is derived as one to a ``many`` form, from
    the app's id.

    Args:
        form_id: The form's id, or the app's.
        principal: The submitter's principal, for a ``per_person`` form.
        nonce: The submit's nonce, for a ``many`` form or an app.

    Raises:
        ValueError: If both a principal and a nonce are given.
    """
    if principal is not None and nonce is not None:
        raise ValueError("a submission's id takes a principal or a nonce, not both")
    if principal is not None:
        parts = ["per_person", form_id, principal]
    elif nonce is not None:
        parts = ["many", form_id, nonce]
    else:
        parts = ["once", form_id]
    return "sub_" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:32]
