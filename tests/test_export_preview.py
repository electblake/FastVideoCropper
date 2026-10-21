from types import SimpleNamespace
from unittest.mock import MagicMock, call

from fastvideocropper.app import Application


def test_export_preview_advances_without_frame_callback():
    player = MagicMock()
    player.position.return_value = 0
    preview = SimpleNamespace(
        player=player,
        job=SimpleNamespace(end=10),
        processing_position=1,
    )

    Application.follow_progress(preview)
    player.position.return_value = 1000
    preview.processing_position = 2
    Application.follow_progress(preview)

    assert player.setPosition.call_args_list == [call(1000), call(2000)]


def test_export_preview_stays_inside_current_segment():
    player = MagicMock()
    player.position.return_value = 5000
    preview = SimpleNamespace(
        player=player,
        job=SimpleNamespace(end=6),
        processing_position=6,
    )

    Application.follow_progress(preview)
    player.setPosition.assert_called_once_with(5999)
    player.position.return_value = 5999
    Application.follow_progress(preview)
    player.setPosition.assert_called_once_with(5999)
