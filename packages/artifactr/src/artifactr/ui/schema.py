"""The form schema: a JSON Schema 2020-12 subset, its UI hints, and its validator.

A form is a :class:`FormSchema`, which models write as JSON Schema and Pydantic emits, beside
:class:`UiHints`, which say how each property is shown and nothing else. The subset is an
allow-list: a keyword it doesn't hold is refused, never ignored, and the refusal names it.

- **The root:** ``type: "object"``, ``title``, ``description``, ``properties`` and ``required``;
  ``additionalProperties`` is false whether or not it is written. A property's name is a letter
  or ``_`` and up to 63 letters, digits, ``_`` or ``-``, and never ``__proto__``,
  ``constructor`` or ``prototype``.
- **A string:** ``minLength``, ``maxLength`` (at most :data:`MAX_LENGTH`), a ``format`` of
  ``date``, ``date-time``, ``email`` or ``uri`` (``http``, ``https`` or ``mailto``), and a
  ``default``.
- **Choices:** an ``enum`` of strings, or a ``oneOf`` of ``{const, title}`` for labelled
  choices, and a ``default``.
- **A number or an integer:** ``minimum``, ``maximum``, ``exclusiveMinimum``,
  ``exclusiveMaximum``, ``multipleOf`` and a ``default``.
- **A boolean:** a ``default``.
- **An array,** of choices only: ``items`` with an ``enum`` or a ``oneOf``, ``uniqueItems``,
  ``minItems``, ``maxItems`` and a ``default``.
- **Every property:** ``title`` and ``description``.

Bounds that no value meets, such as a ``minLength`` over the ``maxLength``, are refused, and
every number is within :data:`MAX_NUMBER` either way.

A schema compiles to a Pydantic model once, kept by its JSON for the 256 schemas used last, and
:meth:`FormSchema.validate_values` checks a submission's values with it. No third-party validator
is involved: the formats and ``multipleOf`` are checked by this module's own small checks, which
the TypeScript side repeats (ADR-0077).
"""

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any, ClassVar, Final, Literal, Self, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    StringConstraints,
    Tag,
    TypeAdapter,
    ValidationError,
    create_model,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticCustomError

from artifactr.core import ValidationFailed
from artifactr.ui._common import MAX_NUMBER, Number, as_number, json_size, refusal
from lattice_core.schema import tag_required

__all__ = [
    "MAX_CHOICES",
    "MAX_LENGTH",
    "MAX_NUMBER",
    "MAX_PROPERTIES",
    "MAX_SCHEMA_BYTES",
    "MAX_VALUES_BYTES",
    "REFUSED_KEYWORDS",
    "RESERVED_NAMES",
    "ArrayProperty",
    "BooleanProperty",
    "Choice",
    "ChoiceProperty",
    "Choices",
    "FieldHints",
    "FormSchema",
    "Format",
    "NumberProperty",
    "Property",
    "Section",
    "StringProperty",
    "UiHints",
    "Widget",
]

MAX_PROPERTIES: Final = 50
"""The most properties a form has."""

MAX_CHOICES: Final = 64
"""The most choices a property offers."""

MAX_LENGTH: Final = 10_000
"""The longest string a form takes, in characters, whatever its ``maxLength`` says."""

MAX_SCHEMA_BYTES: Final = 32 * 1024
"""The largest form, its title, schema and hints as they are stored, in the UTF-8 bytes of their
compact JSON (ADR-0077)."""

MAX_VALUES_BYTES: Final = 64 * 1024
"""The largest submitted values, in the UTF-8 bytes of their compact JSON."""

RESERVED_NAMES: Final = frozenset({"__proto__", "constructor", "prototype"})
"""Property names refused although they fit the pattern: JavaScript objects treat them apart."""

REFUSED_KEYWORDS: Final = frozenset(
    {"$ref", "$defs", "pattern", "if", "then", "else", "allOf", "anyOf", "not"}
)
"""The JSON Schema keywords a model is most likely to write that the subset refuses by name.

Every other keyword outside the subset is refused too, as an extra input at its place; a nested
object and ``format: "password"`` are refused with reasons of their own.
"""

Format = Literal["date", "date-time", "email", "uri"]
"""The string formats the subset checks."""

Widget = Literal["textarea", "select", "checkbox"]
"""How a property may ask to be shown in place of its default: a multi-line text field for a
string, a select for choices that would be segments, and a checkbox for a boolean's switch."""


# ─── the checks the TypeScript side repeats ───────────────────────────────────

# Spelled out, not \d and \s, so each means what it does in JavaScript: a digit is ASCII, and a
# space is any JavaScript calls one; and each matches the whole text, as `$` does in
# JavaScript, where Python's also matches before a final newline.
_DATE: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATE_TIME: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]+)?"
    r"([Zz]|[+-][0-9]{2}:[0-9]{2})$"
)
_SPACE: Final = "\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_LABEL: Final = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL: Final = re.compile(rf"^[^{_SPACE}@]{{1,64}}@{_LABEL}(?:\.{_LABEL})+$")
_URI: Final = re.compile(rf"^(https?://|mailto:)[^{_SPACE}]+$", re.IGNORECASE)
_NAME: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


def _is_date(text: str) -> bool:
    """An RFC 3339 full date, such as ``2026-10-17``, that names a day of the calendar."""
    try:
        return _DATE.fullmatch(text) is not None and bool(date.fromisoformat(text))
    except ValueError:
        return False


def _is_date_time(text: str) -> bool:
    """An RFC 3339 date-time with its offset, such as ``2026-10-17T09:30:00Z``."""
    try:
        return _DATE_TIME.fullmatch(text) is not None and bool(datetime.fromisoformat(text.upper()))
    except ValueError:
        return False


def _is_email(text: str) -> bool:
    """An address: a local part without spaces, ``@``, and a dotted ASCII domain."""
    return len(text) <= 254 and _EMAIL.fullmatch(text) is not None


def _is_uri(text: str) -> bool:
    """A link a person may follow: ``http``, ``https`` or ``mailto``, and no whitespace."""
    return _URI.fullmatch(text) is not None


_FORMATS: Final[dict[Format, Callable[[str], bool]]] = {
    "date": _is_date,
    "date-time": _is_date_time,
    "email": _is_email,
    "uri": _is_uri,
}
"""Each format's check: an RFC 3339 date, or date-time with its offset; an address whose domain
is dotted ASCII labels; an ``http``, ``https`` or ``mailto`` URI. Each is a pattern the
TypeScript side repeats, and a date's day must be on the calendar."""


def _is_multiple(value: float, of: float) -> bool:
    """Whether ``value / of`` is a whole number, to within a billionth of itself, as floats need.

    A quotient too large for a float is no multiple.
    """
    quotient = value / of
    if not math.isfinite(quotient):
        return False
    whole = round(quotient)
    return whole * of == value or abs(quotient - whole) <= 1e-9 * abs(quotient)


# ─── the subset ───────────────────────────────────────────────────────────────


def _positive(value: float) -> float:
    if value <= 0:
        raise PydanticCustomError("greater_than", "Input should be greater than 0")
    return value


def _keywords(value: object) -> dict[str, Any] | None:
    """A schema's keywords, if the value is an object, as it is before it is validated."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _refused(data: dict[str, Any]) -> None:
    """Refuse, by name, the keywords the subset names, before anything else is read."""
    named = sorted(REFUSED_KEYWORDS.intersection(data))
    if named:
        raise PydanticCustomError(
            "refused_keyword",
            "{keywords} not in the form subset",
            {"keywords": f"{', '.join(named)} {'is' if len(named) == 1 else 'are'}"},
        )
    if data.get("format") == "password":
        raise PydanticCustomError(
            "refused_keyword", 'format "password" is refused: a form never asks for a password'
        )


class _Written(BaseModel):
    """Strict, frozen and closed; dumped as written, with what was left out still left out."""

    # A fixed field, an implied ``type`` among them, is always written, so a reader's schema
    # requires it (ADR-0063).
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        serialize_by_alias=True,
        json_schema_extra=tag_required,
    )

    @model_serializer(mode="wrap")
    def _as_written(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        dumped: dict[str, Any] = handler(self)
        return {key: value for key, value in dumped.items() if value is not None}


class _Subset(_Written):
    @model_validator(mode="before")
    @classmethod
    def _refuse(cls, data: object) -> object:
        if (keywords := _keywords(data)) is not None:
            _refused(keywords)
        return data


class _Property(_Subset, ABC):
    kind: ClassVar[str]
    """Which of :data:`Property`'s members it is."""

    title: str | None = None
    description: str | None = None

    @abstractmethod
    def value_type(self) -> Any:
        """The type a value of this property is validated as, in strict mode."""

    @model_validator(mode="after")
    def _default_is_a_value(self) -> Self:
        default: Any = getattr(self, "default", None)
        if default is not None:
            try:
                TypeAdapter(self.value_type(), config=ConfigDict(strict=True)).validate_python(
                    default
                )
            except ValidationError as error:
                raise ValueError(f"the default isn't a value it takes: {_first(error)}") from None
        return self


def _first(error: ValidationError) -> str:
    return error.errors(include_url=False)[0]["msg"]


class StringProperty(_Property):
    """A string, on one line unless its hint asks for a text area."""

    kind: ClassVar[str] = "string"

    type: Literal["string"]
    min_length: Annotated[int, Field(ge=0)] | None = Field(default=None, alias="minLength")
    max_length: Annotated[int, Field(ge=0, le=MAX_LENGTH)] | None = Field(
        default=None, alias="maxLength"
    )
    format: Format | None = None
    default: str | None = None

    @model_validator(mode="after")
    def _met(self) -> Self:
        if _exceeds(self.min_length, self.max_length):
            raise ValueError("minLength is more than maxLength: no string has both")
        return self

    def value_type(self) -> Any:
        """A string of its lengths, at most :data:`MAX_LENGTH`, in its format if it has one."""
        longest = MAX_LENGTH if self.max_length is None else self.max_length
        check = None if self.format is None else _FORMATS[self.format]
        name = self.format

        def formatted(text: str) -> str:
            if check is not None and not check(text):
                raise PydanticCustomError(
                    "format", "Input should be a valid {format}", {"format": name}
                )
            return text

        constraints = StringConstraints(min_length=self.min_length, max_length=longest)
        return Annotated[str, constraints, AfterValidator(formatted)]


class Choice(_Subset):
    """A labelled choice: the value it submits, and the words shown for it."""

    const: str
    title: str


class Choices(_Property):
    """A choice among strings: an ``enum``, or ``oneOf`` labelled choices; ``type`` is implied."""

    kind: ClassVar[str] = "choice"

    type: Literal["string"] = "string"
    enum: Annotated[list[str], Field(min_length=1, max_length=MAX_CHOICES)] | None = None
    one_of: Annotated[list[Choice], Field(min_length=1, max_length=MAX_CHOICES)] | None = Field(
        default=None, alias="oneOf"
    )

    @property
    def offered(self) -> list[str]:
        """The values it offers, in order."""
        if self.enum is not None:
            return self.enum
        return [choice.const for choice in self.one_of or []]

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if (self.enum is None) == (self.one_of is None):
            raise ValueError("choices are an enum or a oneOf, and only one of the two")
        if len(set(self.offered)) != len(self.offered):
            raise ValueError("each choice is offered once")
        return self

    def value_type(self) -> Any:
        """One of the values it offers."""
        offered = self.offered

        def among(value: str) -> str:
            if value not in offered:
                raise PydanticCustomError(
                    "enum", "Input should be one of {expected}", {"expected": ", ".join(offered)}
                )
            return value

        return Annotated[str, AfterValidator(among)]


class ChoiceProperty(Choices):
    """A property that takes one of its choices: segments up to five, else a select."""

    default: str | None = None


class NumberProperty(_Property):
    """A number, or with ``type: "integer"`` a whole one."""

    kind: ClassVar[str] = "number"

    type: Literal["number", "integer"]
    minimum: Number | None = None
    maximum: Number | None = None
    exclusive_minimum: Number | None = Field(default=None, alias="exclusiveMinimum")
    exclusive_maximum: Number | None = Field(default=None, alias="exclusiveMaximum")
    multiple_of: Annotated[Number, AfterValidator(_positive)] | None = Field(
        default=None, alias="multipleOf"
    )
    default: Number | None = None

    @model_validator(mode="after")
    def _met(self) -> Self:
        lows = [(self.minimum, False), (self.exclusive_minimum, True)]
        highs = [(self.maximum, False), (self.exclusive_maximum, True)]
        for low, open_low in lows:
            for high, open_high in highs:
                if (
                    low is not None
                    and high is not None
                    and (low > high or (low == high and (open_low or open_high)))
                ):
                    raise ValueError("its bounds leave no number between them")
        return self

    def value_type(self) -> Any:
        """A number, or an int, within its bounds and a multiple of its ``multipleOf``."""
        of = self.multiple_of

        def multiple(value: float) -> float:
            if of is not None and not _is_multiple(value, of):
                raise PydanticCustomError(
                    "multiple_of",
                    "Input should be a multiple of {multiple_of}",
                    {"multiple_of": of},
                )
            return value

        bounds = Field(
            ge=self.minimum, le=self.maximum, gt=self.exclusive_minimum, lt=self.exclusive_maximum
        )
        number = BeforeValidator(as_number)
        if self.type == "integer":
            return Annotated[int, number, bounds, AfterValidator(multiple)]
        return Annotated[float, number, bounds, AfterValidator(multiple)]


class BooleanProperty(_Property):
    """A yes or no, as a switch unless its hint asks for a checkbox."""

    kind: ClassVar[str] = "boolean"

    type: Literal["boolean"]
    default: bool | None = None

    def value_type(self) -> Any:
        """A bool."""
        return bool


class ArrayProperty(_Property):
    """Some of its items' choices, as checkboxes."""

    kind: ClassVar[str] = "array"

    type: Literal["array"]
    items: Choices
    unique_items: bool | None = Field(default=None, alias="uniqueItems")
    min_items: Annotated[int, Field(ge=0)] | None = Field(default=None, alias="minItems")
    max_items: Annotated[int, Field(ge=0)] | None = Field(default=None, alias="maxItems")
    default: list[str] | None = None

    @model_validator(mode="after")
    def _met(self) -> Self:
        if _exceeds(self.min_items, self.max_items):
            raise ValueError("minItems is more than maxItems: no list has both")
        if self.unique_items and _exceeds(self.min_items, len(self.items.offered)):
            raise ValueError("minItems is more than the choices, each chosen once")
        return self

    def value_type(self) -> Any:
        """A list of its items' choices, as many as it allows, each once if they are unique."""
        offered, unique = self.items.offered, bool(self.unique_items)

        def chosen(values: list[str]) -> list[str]:
            if unknown := [value for value in values if value not in offered]:
                raise PydanticCustomError(
                    "enum",
                    "{unknown} not among {expected}",
                    {"unknown": ", ".join(unknown), "expected": ", ".join(offered)},
                )
            if unique and len(set(values)) != len(values):
                raise PydanticCustomError("unique_items", "Each choice should be chosen once")
            return values

        sizes = Field(min_length=self.min_items, max_length=self.max_items)
        return Annotated[list[str], sizes, AfterValidator(chosen)]


def _kind(value: Any) -> str | None:
    """Which kind of property a value is: choices by their keywords, the rest by ``type``."""
    if isinstance(value, _Property):
        return value.kind
    data = _keywords(value)
    if data is None:
        return None
    if "enum" in data or "oneOf" in data:
        return "choice"
    kind = data.get("type")
    if kind == "integer":
        return "number"
    return kind if isinstance(kind, str) else None


def _exceeds(least: int | None, most: int | None) -> bool:
    return least is not None and most is not None and least > most


def _named(name: str) -> str:
    if not _NAME.fullmatch(name) or name in RESERVED_NAMES:
        raise PydanticCustomError(
            "property_name",
            "A property's name is a letter or _, then up to 63 letters, digits, _ or -, and not "
            "__proto__, constructor or prototype",
        )
    return name


def _not_nested(value: object) -> object:
    if (data := _keywords(value)) is not None:
        _refused(data)
        if data.get("type") == "object" or "properties" in data:
            raise PydanticCustomError(
                "nested_object",
                "a property can't be an object: nested objects are not in the subset",
            )
    return value


Property = Annotated[
    Annotated[StringProperty, Tag("string")]
    | Annotated[ChoiceProperty, Tag("choice")]
    | Annotated[NumberProperty, Tag("number")]
    | Annotated[BooleanProperty, Tag("boolean")]
    | Annotated[ArrayProperty, Tag("array")],
    Discriminator(
        _kind,
        custom_error_type="property_type",
        custom_error_message=(
            'Each property is a "string", "number", "integer", "boolean" or "array", '
            "or choices with an enum or a oneOf"
        ),
    ),
    BeforeValidator(_not_nested),
]
"""One property of a form, told apart by its ``type``, or as choices by ``enum`` or ``oneOf``."""


type _Values = type[BaseModel]
"""A compiled form's model of its values. Named here, since a schema's own ``type`` field hides
the builtin in its class."""


class FormSchema(_Subset):
    """A form: a JSON Schema 2020-12 object in the subset, compiled once to check values.

    Validating one refuses, by name, every keyword outside the subset, a property the subset
    doesn't hold, more than :data:`MAX_PROPERTIES` properties, a name outside the pattern, a
    ``required`` name that isn't a property, a ``default`` its property doesn't take, and bounds
    no value meets. ``additionalProperties`` is false, written or not. A form with no
    properties is a button. Its size counts towards its form's, :data:`MAX_SCHEMA_BYTES`.
    """

    type: Literal["object"] = "object"
    title: str | None = None
    description: str | None = None
    properties: Annotated[
        dict[Annotated[str, AfterValidator(_named)], Property],
        Field(max_length=MAX_PROPERTIES),
    ] = {}
    required: list[str] = []
    additional_properties: Literal[False] = Field(default=False, alias="additionalProperties")

    @model_validator(mode="after")
    def _checked(self) -> Self:
        if unknown := [name for name in self.required if name not in self.properties]:
            raise ValueError(f"required names {', '.join(unknown)}, not a property")
        if len(set(self.required)) != len(self.required):
            raise ValueError("required names each property once")
        return self

    def validate_values(self, values: JsonValue) -> dict[str, JsonValue]:
        """Check a submission's values against the form, and return them as they were given.

        Raises:
            ValidationFailed: If they don't fit: each error's ``loc`` is the property's name
                (or empty, for values that aren't an object or are over
                :data:`MAX_VALUES_BYTES`), as Pydantic writes it, so each can be shown under
                its field.
        """
        if (size := json_size(values)) > MAX_VALUES_BYTES:
            message = f"the values are {size} bytes, over the limit of {MAX_VALUES_BYTES}"
            raise ValidationFailed(message, [{"type": "too_long", "loc": [], "msg": message}])
        try:
            _compiled(self.model_dump_json()).model_validate(values)
        except ValidationError as error:
            raise refusal("invalid values", error) from error
        return cast("dict[str, JsonValue]", values)


@lru_cache(maxsize=256)
def _compiled(schema: str) -> _Values:
    """A schema's model of its values, by the schema's JSON: compiled once while it is in use."""
    return _compile(FormSchema.model_validate_json(schema))


def _compile(schema: FormSchema) -> _Values:
    fields: dict[str, Any] = {
        # Python names of its own, so that any property name is a field: Pydantic reports the
        # property's name, its alias, in an error's loc.
        f"p{index}": (
            prop.value_type(),
            Field(alias=name) if name in schema.required else Field(default=None, alias=name),
        )
        for index, (name, prop) in enumerate(schema.properties.items())
    }
    config = ConfigDict(extra="forbid", strict=True)
    return create_model("FormValues", __config__=config, **fields)


# ─── UI hints ─────────────────────────────────────────────────────────────────


class FieldHints(_Written):
    """How one property is shown: its widget, a placeholder and help, all plain text."""

    widget: Widget | None = None
    placeholder: str | None = None
    help: str | None = None


class Section(_Written):
    """A titled group of properties, by name."""

    title: str
    properties: list[str]


_WIDGETS: Final[dict[Widget, str]] = {
    "textarea": "string",
    "select": "choice",
    "checkbox": "boolean",
}
"""The kind of property each widget fits."""


class UiHints(_Written):
    """How a form is shown, and nothing else.

    A hint names a component of the kit, or carries plain text: none carries a colour, a
    class, HTML or a URL. ``fields`` hints each property by name, ``order`` and ``sections``
    arrange them, and ``submit_label`` names the form's button.
    """

    fields: dict[str, FieldHints] = {}
    order: list[str] | None = None
    sections: list[Section] | None = None
    submit_label: str | None = None

    def check(self, schema: FormSchema) -> None:
        """Check that every name is the schema's and every widget fits its property.

        Raises:
            ValueError: If a hint names a property the schema hasn't, or asks for a widget
                that doesn't fit its property.
        """
        order, sectioned = self.order or [], self._sectioned()
        for named, where in ((order, "order"), (sectioned, "sections")):
            if len(set(named)) != len(named):
                raise ValueError(f"ui's {where} names a property twice")
        named = [*self.fields, *order, *sectioned]
        if unknown := sorted({name for name in named if name not in schema.properties}):
            raise ValueError(f"ui names {', '.join(unknown)}, not a property")
        for name, hints in self.fields.items():
            kind = schema.properties[name].kind
            if hints.widget is not None and _WIDGETS[hints.widget] != kind:
                raise ValueError(f"ui gives {name} a {hints.widget}, which a {kind} can't take")

    def _sectioned(self) -> list[str]:
        return [name for section in self.sections or [] for name in section.properties]
