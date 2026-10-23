"""The patch builder and the rebase, without a workspace: each change scoped to its element."""

from artifactr.excalidraw import DiagramFile, element_patch, rebase, reconcile
from artifactr.excalidraw.patches import won
from tests.excalidraw.scenes import diagram, element, moved

R1, R2 = element("r1"), element("r2")
IMAGE = DiagramFile(sha256="c" * 64, size=3, media_type="image/png")


def test_a_patch_tests_each_element_it_replaces_keeps_what_it_leaves_out_and_adds_the_rest() -> (
    None
):
    base = diagram(R1, R2)
    new = element("n1")
    patch = element_patch(base, {"r1": moved(R1, 5), "n1": new}, {IMAGE.sha256: IMAGE})
    assert patch.ops == (
        {"op": "test", "path": "/elements/r1/version", "value": 1},
        {"op": "replace", "path": "/elements/r1", "value": moved(R1, 5).model_dump(mode="json")},
        {"op": "add", "path": "/elements/n1", "value": new.model_dump(mode="json")},
        {"op": "add", "path": f"/files/{IMAGE.sha256}", "value": IMAGE.model_dump()},
    )


def test_nothing_changed_is_an_empty_patch() -> None:
    base = diagram(R1).model_copy(update={"files": {IMAGE.sha256: IMAGE}})
    assert element_patch(base, base.elements, base.files).ops == ()


def test_the_higher_version_wins_and_at_one_version_the_lower_nonce() -> None:
    assert won(element("a", version=3), element("a", version=2, nonce=1))
    assert not won(element("a", version=2), element("a", version=3))
    assert won(element("a", nonce=1), element("a", nonce=2))
    assert not won(element("a", nonce=2), element("a", nonce=1))


def test_reconcile_keeps_every_element_of_either() -> None:
    local = {"r1": moved(R1, 5), "l1": element("l1")}
    remote = {"r1": R1, "x1": element("x1")}
    assert reconcile(local, remote) == {
        "r1": moved(R1, 5),
        "x1": element("x1"),
        "l1": element("l1"),
    }


def test_a_rebase_keeps_a_new_element_and_what_the_writer_left_alone() -> None:
    base = diagram(R1, R2)
    head = diagram(R1, moved(R2, 9))
    mine = {**base.elements, "n1": element("n1")}
    assert rebase(base, mine, head) == {**head.elements, "n1": element("n1")}


def test_one_written_as_true_or_as_a_float_is_a_change() -> None:
    for value in (True, 1.0):
        changed = element("r1", weight=value)
        patch = element_patch(diagram(element("r1", weight=1)), {"r1": changed})
        assert patch.ops[1] == {
            "op": "replace",
            "path": "/elements/r1",
            "value": changed.model_dump(mode="json"),
        }


def test_a_rebase_counts_a_number_rewritten_as_a_float_as_the_writers_change() -> None:
    # One version on both sides: only the JSON text tells 10.0 from 10, as Python's == can't.
    base = diagram(element("r1", width=10))
    head = diagram(element("r1", width=10, nonce=99))
    mine = {"r1": element("r1", width=10.0)}
    rebased = rebase(base, mine, head)
    assert rebased["r1"].model_dump(mode="json")["width"] == 10.0, "counted as the writer's"
    assert rebased["r1"].version == 2, "sent above the head's version"
    # Left alone, the writer's element is the head's, whatever its nonce: nothing to send.
    untouched = rebase(base, base.elements, head)
    assert untouched == head.elements
    assert untouched["r1"].version_nonce == 99
