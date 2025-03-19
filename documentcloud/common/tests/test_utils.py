# Standard Library
from unittest.mock import Mock

# Third Party
import pymupdf

# DocumentCloud
from documentcloud.common.utils import graft_page


def test_graft_page():
    mock_page = Mock()
    mock_page.rect.width = 700
    mock_page.rect.height = 905
    positions = [
        {
            "text": "hello",
            "x1": 0.1,
            "y1": 0.1,
            "x2": 0.3,
            "y2": 0.2,
        },
        {
            "text": "world",
            "x1": 0.4,
            "y1": 0.1,
            "x2": 0.6,
            "y2": 0.2,
        },
    ]

    graft_page(positions, mock_page)
    mock_page.insert_text.assert_any_call(
        point=pymupdf.Point(
            positions[0]["x1"] * mock_page.rect.width,
            positions[0]["y2"] * mock_page.rect.height,
        ),
        text="hello",
        fontsize=66,
        fill_opacity=0,
    )
    mock_page.insert_text.assert_any_call(
        point=pymupdf.Point(
            positions[1]["x1"] * mock_page.rect.width,
            positions[1]["y2"] * mock_page.rect.height,
        ),
        text="world",
        fontsize=58,
        fill_opacity=0,
    )
