"""Colour as the validator reads it: sRGB with alpha, contrast, mixing, and CIEDE2000 distance.

The same arithmetic as the UI's token tests (``web/ui/src/test/colours.ts``), so a kit is held to
the floors the default is: WCAG's contrast ratio, Machado, Oliveira and Fernandes' (2009)
simulations of colour-vision deficiency at full severity, and Sharma, Wu and Dalal's CIEDE2000.
"""

import math
from dataclasses import dataclass
from typing import Literal

Deficiency = Literal["protanopia", "deuteranopia", "tritanopia"]

DEFICIENCIES: tuple[Deficiency, ...] = ("protanopia", "deuteranopia", "tritanopia")

_SIMULATION: dict[Deficiency, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.01182, 0.04294, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.3039),
    ),
}


@dataclass(frozen=True)
class Rgba:
    """A colour in sRGB, each channel from 0 to 1, with its alpha."""

    r: float
    g: float
    b: float
    a: float = 1.0

    @classmethod
    def hex(cls, value: str, alpha: float = 1.0) -> "Rgba":
        """A colour from ``#rrggbb``."""
        r, g, b = (int(value[at : at + 2], 16) / 255 for at in (1, 3, 5))
        return cls(r, g, b, alpha)

    def over(self, backdrop: "Rgba") -> "Rgba":
        """This colour composited over an opaque backdrop, as the page draws it."""
        a = self.a
        return Rgba(
            self.r * a + backdrop.r * (1 - a),
            self.g * a + backdrop.g * (1 - a),
            self.b * a + backdrop.b * (1 - a),
        )


def mix(one: Rgba, share: float, other: Rgba) -> Rgba:
    """``color-mix(in srgb, one share, other)``, as base.css mixes the derived colours."""
    total = one.a * share + other.a * (1 - share)
    if total == 0:
        return Rgba(0, 0, 0, 0)

    def channel(x: float, y: float) -> float:
        return (x * one.a * share + y * other.a * (1 - share)) / total

    return Rgba(channel(one.r, other.r), channel(one.g, other.g), channel(one.b, other.b), total)


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: Rgba) -> float:
    """WCAG's relative luminance of an opaque colour."""
    r, g, b = (_linear(c) for c in (colour.r, colour.g, colour.b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one: Rgba, other: Rgba) -> float:
    """WCAG's contrast ratio of two opaque colours, from 1 to 21."""
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b
    z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else ((24389 / 27) * t + 16) / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e2000(one: tuple[float, float, float], other: tuple[float, float, float]) -> float:
    """CIEDE2000 between two L*a*b* colours (Sharma, Wu and Dalal, 2005)."""
    l1, a1, b1 = one
    l2, a2, b2 = other
    c_mean = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_mean**7 / (c_mean**7 + 25**7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1, c2 = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1 = math.degrees(math.atan2(b1, a1p)) % 360 if c1 else 0.0
    h2 = math.degrees(math.atan2(b2, a2p)) % 360 if c2 else 0.0
    dl, dc = l2 - l1, c2 - c1
    dh = 0.0
    if c1 * c2:
        dh = h2 - h1
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
    d_h = 2 * math.sqrt(c1 * c2) * math.sin(math.radians(dh / 2))
    l_mean, c_mean_p = (l1 + l2) / 2, (c1 + c2) / 2
    h_mean = h1 + h2
    if c1 * c2:
        if abs(h1 - h2) > 180:
            h_mean = (h1 + h2 + (360 if h1 + h2 < 360 else -360)) / 2
        else:
            h_mean = (h1 + h2) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_mean - 30))
        + 0.24 * math.cos(math.radians(2 * h_mean))
        + 0.32 * math.cos(math.radians(3 * h_mean + 6))
        - 0.2 * math.cos(math.radians(4 * h_mean - 63))
    )
    rotation = (
        -math.sin(math.radians(60 * math.exp(-(((h_mean - 275) / 25) ** 2))))
        * 2
        * math.sqrt(c_mean_p**7 / (c_mean_p**7 + 25**7))
    )
    sl = 1 + (0.015 * (l_mean - 50) ** 2) / math.sqrt(20 + (l_mean - 50) ** 2)
    sc = 1 + 0.045 * c_mean_p
    sh = 1 + 0.015 * c_mean_p * t
    return math.sqrt(
        (dl / sl) ** 2 + (dc / sc) ** 2 + (d_h / sh) ** 2 + rotation * (dc / sc) * (d_h / sh)
    )


def distance(one: Rgba, other: Rgba, deficiency: Deficiency | None = None) -> float:
    """How far apart two opaque colours look, to every reader or to one with a deficiency."""

    def seen(colour: Rgba) -> tuple[float, float, float]:
        rgb = (_linear(colour.r), _linear(colour.g), _linear(colour.b))
        if deficiency is None:
            return _lab(rgb)
        matrix = _SIMULATION[deficiency]
        simulated = tuple(
            min(1.0, max(0.0, sum(w * c for w, c in zip(row, rgb, strict=True)))) for row in matrix
        )
        return _lab((simulated[0], simulated[1], simulated[2]))

    return delta_e2000(seen(one), seen(other))
