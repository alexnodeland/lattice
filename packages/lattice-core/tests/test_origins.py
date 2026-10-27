"""web_origin and origins: an origin as a browser compares it, and nothing that isn't one."""

import pytest

from lattice_core.origins import LOOPBACK, origins, web_origin, web_origins


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://portal.example", "https://portal.example"),
        ("https://portal.example/", "https://portal.example"),
        ("HTTPS://Portal.Example:443", "https://portal.example"),
        ("https://portal.example:8443", "https://portal.example:8443"),
        ("https://my-machine.my-tailnet.ts.net", "https://my-machine.my-tailnet.ts.net"),
        ("http://127.0.0.1:8800", "http://127.0.0.1:8800"),
        ("http://127.0.0.1:80", "http://127.0.0.1"),
        ("http://localhost:8800/", "http://localhost:8800"),
        ("http://LocalHost:8800", "http://localhost:8800"),
        ("http://[::1]:8800", "http://[::1]:8800"),
        ("https://[::1]", "https://[::1]"),
    ],
)
def test_an_origin_is_kept_as_a_browser_compares_it(url: str, origin: str) -> None:
    assert web_origin(url) == origin


@pytest.mark.parametrize(
    ("url", "said"),
    [
        ("http://portal.example", "give it https, or http on loopback"),
        ("http://192.168.1.20:8800", "an IP address that isn't loopback"),
        ("https://10.0.0.1", "an IP address that isn't loopback"),
        ("https://[fe80::1]", "an IP address that isn't loopback"),
        ("ftp://portal.example", "give it https"),
        ("javascript:alert(1)", "a host, with no user or password"),
        ("/portal", "a host, with no user or password"),
        ("https://", "a host, with no user or password"),
        ("https://user@portal.example", "a host, with no user or password"),
        ("https://user:secret@portal.example", "a host, with no user or password"),
        ("https://portal.example/app", "no path, query or fragment"),
        ("https://portal.example/?x=1", "no path, query or fragment"),
        ("https://portal.example/#top", "no path, query or fragment"),
        ("https://*.example", "no wildcard or escape"),
        ("https://portal.example:*", "no wildcard or escape"),
        ("https://portal%2eexample", "no wildcard or escape"),
        ("https://portal.example:99999", "out of range"),
        ("https://a.example;script-src", "ASCII letters, digits"),
        ("https://a.example,https://b.example", "ASCII letters, digits"),
        ("https://a.example https://b.example", "ASCII letters, digits"),
        ("https://a.example'", "ASCII letters, digits"),
        ("https://bücher.example", "ASCII letters, digits"),
        ("https://a_b.example", "ASCII letters, digits"),
        ("https://-a.example", "a host name of DNS labels"),
        ("https://a..example", "a host name of DNS labels"),
        ("https://portal.example:x", "Port could not be cast"),
        ("", "a host, with no user or password"),
    ],
)
def test_what_is_no_web_origin_is_refused_and_named(url: str, said: str) -> None:
    with pytest.raises(ValueError, match=said) as refused:
        web_origin(url, what="the portal")
    assert str(refused.value).startswith("the portal is an origin, such as https://portal.example")


def test_loopback_is_this_machines_three_names() -> None:
    assert {"localhost", "127.0.0.1", "::1"} == LOOPBACK


def test_origins_are_each_checked_once_and_never_the_canonical() -> None:
    csv = " https://a.example, https://A.example:443/ ,http://127.0.0.1:8800,,https://b.example"
    assert origins(csv, canonical="http://127.0.0.1:8800/") == (
        "https://a.example",
        "https://b.example",
    )
    assert origins("") == ()
    assert origins(" , ") == ()
    assert origins("https://a.example", canonical=None) == ("https://a.example",)


def test_origins_past_the_limit_are_refused_once_repeats_are_left_out() -> None:
    three = "https://a.example,https://b.example,https://c.example"
    assert len(origins(f"{three},https://a.example", limit=3)) == 3
    with pytest.raises(ValueError, match="the extras name 3 origins: at most 2"):
        origins(three, what="the extras", limit=2)


def test_an_origin_in_the_list_that_isnt_one_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="the extras is an origin, such as"):
        origins("https://a.example, http://lan.local:8800", what="the extras")


def test_one_origin_or_several_are_each_kept_once_in_order() -> None:
    assert web_origins("https://a.example/") == ("https://a.example",)
    assert web_origins(["https://b.example", "HTTPS://A.example:443", "https://b.example"]) == (
        "https://b.example",
        "https://a.example",
    )
    with pytest.raises(ValueError, match=r"the portal is an origin, such as .*: name one"):
        web_origins([], what="the portal")
    with pytest.raises(ValueError, match="the portal is an origin"):
        web_origins(["https://a.example", "http://a.example"], what="the portal")
