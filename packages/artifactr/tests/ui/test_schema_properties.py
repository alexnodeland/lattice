"""Properties of the schema subset, over schemas and values Hypothesis makes.

Any schema the subset allows compiles and reads back unchanged; values made to fit one pass; a
value made not to fit is refused at its property; and every keyword outside the subset is refused
by name, wherever it is written.
"""

import re
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from artifactr.core import ValidationFailed
from artifactr.ui.schema import REFUSED_KEYWORDS, RESERVED_NAMES, FormSchema
from tests.ui.refusals import locs

Draw = st.DrawFn
Made = tuple[dict[str, Any], st.SearchStrategy[Any], Any]
"""A property's schema, a strategy for the values it takes, and a value it refuses."""

# Built from the pattern's own characters: from_regex and a codec's alphabet make Hypothesis map
# the whole of Unicode first, which a fresh CI runner can't do inside a test's timeout.
FIRST = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
NAMES = st.one_of(
    st.builds(
        lambda first, rest: first + rest,
        st.sampled_from(FIRST),
        st.text(st.sampled_from(FIRST + "0123456789-"), max_size=11),
    ).filter(lambda name: name not in RESERVED_NAMES),
    st.sampled_from(["model_config", "_private", "schema", "type", "p0", "__init__", "a-b"]),
)
"""Property names, the awkward ones among them: any the pattern allows is a field."""

WORDS = st.text(st.characters(exclude_categories=["Cs"]), max_size=8)

SAMPLES = {
    "date": st.sampled_from(["2026-10-17", "2024-02-29", "1999-12-31"]),
    "date-time": st.sampled_from(["2026-10-17T09:30:00Z", "2026-10-17T09:30:00.5+02:00"]),
    "email": st.sampled_from(["alice@example.com", "a.b+c@mail.example.org"]),
    "uri": st.sampled_from(["https://example.com/a?b=c", "mailto:alice@example.com", "HTTP://x.y"]),
}


@st.composite
def strings(draw: Draw) -> Made:
    format = draw(st.none() | st.sampled_from(sorted(SAMPLES)))
    if format is not None:
        return {"type": "string", "format": format}, SAMPLES[format], "not a " + format
    shortest = draw(st.integers(0, 4))
    longest = draw(st.none() | st.integers(shortest, 12))
    schema: dict[str, Any] = {"type": "string", "minLength": shortest}
    if longest is not None:
        schema["maxLength"] = longest
    return (
        schema,
        WORDS.filter(lambda word: shortest <= len(word) <= (12 if longest is None else longest)),
        7,
    )


@st.composite
def choices(draw: Draw) -> Made:
    offered = draw(st.lists(WORDS.filter(bool), min_size=1, max_size=6, unique=True))
    if draw(st.booleans()):
        schema: dict[str, Any] = {"enum": offered}
    else:
        schema = {"type": "string", "oneOf": [{"const": v, "title": v.upper()} for v in offered]}
    if draw(st.booleans()):
        schema["default"] = draw(st.sampled_from(offered))
    return schema, st.sampled_from(offered), "".join(offered) + "?"


@st.composite
def numbers(draw: Draw) -> Made:
    if draw(st.booleans()):
        low = draw(st.integers(-100, 100))
        high = draw(st.integers(low, low + 100))
        schema: dict[str, Any] = {"type": "integer", "minimum": low, "maximum": high}
        return schema, st.integers(low, high), "1"
    of = draw(st.sampled_from([0.1, 0.25, 0.5, 2, 3]))
    schema = {"type": "number", "multipleOf": of, "exclusiveMinimum": -1000, "maximum": 1000}
    return schema, st.integers(int(-999 / of), int(1000 / of)).map(lambda k: k * of), True


@st.composite
def booleans(draw: Draw) -> Made:
    schema: dict[str, Any] = {"type": "boolean"}
    if draw(st.booleans()):
        schema["default"] = draw(st.booleans())
    return schema, st.booleans(), "true"


@st.composite
def arrays(draw: Draw) -> Made:
    offered = draw(st.lists(WORDS.filter(bool), min_size=1, max_size=5, unique=True))
    unique = draw(st.booleans())
    fewest = draw(st.integers(0, len(offered)))
    most = draw(st.integers(fewest, len(offered)))
    schema = {
        "type": "array",
        "items": {"enum": offered},
        "uniqueItems": unique,
        "minItems": fewest,
        "maxItems": most,
    }
    values = st.lists(st.sampled_from(offered), min_size=fewest, max_size=most, unique=unique)
    return schema, values, ["".join(offered) + "?"]


PROPERTIES = st.one_of(strings(), choices(), numbers(), booleans(), arrays())


@st.composite
def described(draw: Draw) -> Made:
    """A property, with a title and a description sometimes."""
    schema, values, wrong = draw(PROPERTIES)
    for keyword in ("title", "description"):
        if draw(st.booleans()):
            schema = {**schema, keyword: draw(WORDS)}
    return schema, values, wrong


@st.composite
def forms(draw: Draw) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """A schema the subset allows, values that fit it, and a value each property refuses."""
    made = draw(st.dictionaries(NAMES, described(), max_size=6))
    required = [name for name in made if draw(st.booleans())]
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {n: s for n, (s, _, _) in made.items()},
    }
    if required or draw(st.booleans()):
        schema["required"] = required
    values = {
        name: draw(strategy)
        for name, (_, strategy, _) in made.items()
        if name in required or draw(st.booleans())
    }
    return schema, values, {name: wrong for name, (_, _, wrong) in made.items()}


@settings(max_examples=150, deadline=None)
@given(forms())
def test_any_allowed_schema_compiles_and_reads_back_unchanged(form: Any) -> None:
    schema, _, _ = form
    validated = FormSchema.model_validate(schema)
    assert FormSchema.model_validate(validated.model_dump(mode="json")) == validated
    dumped = validated.model_dump(mode="json")
    assert FormSchema.model_validate(dumped).model_dump(mode="json") == dumped
    assert dumped["properties"].keys() == schema["properties"].keys()


@settings(max_examples=150, deadline=None)
@given(forms())
def test_values_made_to_fit_pass(form: Any) -> None:
    schema, values, _ = form
    assert FormSchema.model_validate(schema).validate_values(values) == values


@settings(max_examples=150, deadline=None)
@given(forms().filter(lambda form: form[0]["properties"]), st.data())
def test_a_value_that_does_not_fit_is_refused_at_its_property(
    form: Any, data: st.DataObject
) -> None:
    schema, values, wrong = form
    name = data.draw(st.sampled_from(sorted(schema["properties"])))
    with pytest.raises(ValidationFailed) as refused:
        FormSchema.model_validate(schema).validate_values({**values, name: wrong[name]})
    assert locs(refused.value) == [[name]]


@settings(max_examples=150, deadline=None)
@given(forms().filter(lambda form: form[0].get("required")), st.data())
def test_a_missing_required_value_is_refused_at_its_property(
    form: Any, data: st.DataObject
) -> None:
    schema, values, _ = form
    name = data.draw(st.sampled_from(schema["required"]))
    without = {key: value for key, value in values.items() if key != name}
    with pytest.raises(ValidationFailed) as refused:
        FormSchema.model_validate(schema).validate_values(without)
    assert locs(refused.value) == [[name]]


@settings(max_examples=150, deadline=None)
@given(forms().filter(lambda form: form[0]["properties"]), st.data())
def test_every_refused_keyword_is_named_wherever_it_is_written(
    form: Any, data: st.DataObject
) -> None:
    schema, _, _ = form
    keyword = data.draw(st.sampled_from(sorted(REFUSED_KEYWORDS)))
    name = data.draw(st.none() | st.sampled_from(sorted(schema["properties"])))
    if name is None:
        schema = {**schema, keyword: {}}
    else:
        schema["properties"][name] = {**schema["properties"][name], keyword: {}}
    with pytest.raises(ValidationError, match=f"{re.escape(keyword)} is not in the form subset"):
        FormSchema.model_validate(schema)


@settings(max_examples=150, deadline=None)
@given(forms().filter(lambda form: form[0]["properties"]), st.data())
def test_any_keyword_outside_the_subset_is_refused_at_its_place(
    form: Any, data: st.DataObject
) -> None:
    schema, _, _ = form
    allowed = {"title", "description", "type", "default", "items", "enum", "format", "properties"}
    keyword = data.draw(
        st.text("abcdefghijklmnopqrstuvwxyzA", min_size=1, max_size=10).filter(
            lambda word: (
                word not in allowed | REFUSED_KEYWORDS
                and not word.endswith(("Length", "Items", "imum", "Of"))
            )
        )
    )
    name = data.draw(st.sampled_from(sorted(schema["properties"])))
    schema["properties"][name] = {**schema["properties"][name], keyword: 1}
    with pytest.raises(ValidationError) as refused:
        FormSchema.model_validate(schema)
    places = [(error["loc"][1], error["loc"][-1]) for error in refused.value.errors()]
    assert (name, keyword) in places
