"""The PNG of one colour that a blank page is drawn as."""

import pytest

from artifactr.files.app.png import SIGNATURE, solid
from tests.files.app.png import pixels


def test_a_colour_is_three_bytes_or_four_with_alpha() -> None:
    assert pixels(solid(3, 2, b"\x01\x02\x03")) == (3, 2, b"\x01\x02\x03")
    transparent = solid(2, 2, b"\x00" * 4)
    assert transparent.startswith(SIGNATURE)
    assert pixels(transparent) == (2, 2, b"\x00" * 4)
    with pytest.raises(ValueError, match="three or four bytes, not 5"):
        solid(1, 1, b"\x00" * 5)
