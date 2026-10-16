"""The tags of a model request, and the tenant-workspace tag read back."""

import pytest

from lattice_core.tags import parse_workspace_tag, request_tags, workspace_tag

IDS = [
    ("acme", "launch"),
    ("acme/eu", "q3/plan"),
    ("a,b", "c,d"),
    ("100%", "a%2Fb"),
    ("a b", "x y"),
    ("naïve", "東京~x"),
]


@pytest.mark.parametrize(
    ("tenant", "workspace", "tag"),
    [
        ("acme", "launch", "tenant-workspace:acme/launch"),
        ("acme/eu", "q3,plan", "tenant-workspace:acme%2Feu/q3%2Cplan"),
        ("100%", "a%2Fb", "tenant-workspace:100%25/a%252Fb"),
        ("a b", "naïve~x", "tenant-workspace:a%20b/na%C3%AFve~x"),
    ],
)
def test_each_id_is_percent_encoded(tenant: str, workspace: str, tag: str) -> None:
    assert workspace_tag(tenant, workspace) == tag


@pytest.mark.parametrize(("tenant", "workspace"), IDS)
def test_a_tag_reads_back_its_ids(tenant: str, workspace: str) -> None:
    tag = workspace_tag(tenant, workspace)
    assert tag.count("/") == 1
    assert "," not in tag
    assert parse_workspace_tag(tag) == (tenant, workspace)


@pytest.mark.parametrize(
    "tag",
    [
        "tenant:acme",
        "workspace:launch",
        "rule:app:review",
        "artifactr",
        "tenant-workspace:acme",
        "tenant-workspace:%FF/x",
    ],
)
def test_other_tags_read_as_none(tag: str) -> None:
    assert parse_workspace_tag(tag) is None


def test_a_requests_tags_name_its_tenant_its_workspace_and_both() -> None:
    assert request_tags("acme/eu", "q3") == [
        "tenant:acme/eu",
        "workspace:q3",
        "tenant-workspace:acme%2Feu/q3",
    ]
