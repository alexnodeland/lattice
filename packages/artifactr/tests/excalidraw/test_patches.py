"""The patch builder and the rebase, without a workspace: each change scoped to its element."""

from artifactr.excalidraw import DiagramFile, element_patch, rebase, reconcile
from artifactr.excalidraw.patches import won
from tests.excalidraw.scenes import diagram, element, moved

R1, R2 = element("r1"), element("r2")
IMAGE = DiagramFile(sha256="c" * 64, size=3, media_type="image/png")


def test_a_patch_tests_each_element_it_replaces_or_removes_and_adds_the_rest() -> None:
    base = diagram(R1, R2)
    new = element("n1")
    patch = element_patch(base, {"r1": moved(R1, 5), "n1": new}, {IMAGE.sha256: IMAGE})
    assert patch.ops == (
        {"op": "test", "path": "/elements/r1/version", "value": 1},
        {"op": "replace", "path": "/elements/r1", "value": moved(R1, 5).model_dump(mode="json")},
        {"op": "add", "path": "/elements/n1", "value": new.model_dump(mode="json")},
        {"op": "test", "path": "/elements/r2/version", "value": 1},
        {"op": "remove", "path": "/elements/r2"},
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
