from grantr.core import ServicePrincipal, issue, key_id, verify

CI = ServicePrincipal(id="ci")


def test_a_key_is_an_id_and_32_random_bytes_and_only_its_digest_is_kept() -> None:
    key, stored = issue("acme", CI)
    prefix, _, rest = key.partition("_sk_")
    found, _, secret = rest.partition("_")
    assert (prefix, found, len(bytes.fromhex(secret))) == ("grantr", stored.id, 32)
    assert secret not in stored.model_dump_json()
    assert (stored.tenant, stored.principal) == ("acme", CI)
    assert key_id(key) == stored.id
    assert verify(key, stored)


def test_two_keys_differ() -> None:
    first, _ = issue("acme", CI)
    second, _ = issue("acme", CI)
    assert first != second


def test_a_key_with_another_secret_or_id_isnt_the_one_stored() -> None:
    key, stored = issue("acme", CI)
    other, _ = issue("acme", CI)
    assert not verify(f"{key[:-1]}{'0' if key[-1] != '0' else '1'}", stored)
    assert not verify(other, stored)


def test_what_isnt_a_key_has_no_id() -> None:
    key, stored = issue("acme", CI)
    for text in ("", "grantr_sk_x_y", key.upper(), f"{key}0", key.replace("grantr", "other")):
        assert key_id(text) is None
        assert not verify(text, stored)
