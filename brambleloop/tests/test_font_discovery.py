"""Portable font discovery never converts an unavailable font into a pass."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from brambleloop.publish import charts


def test_configured_font_is_loaded_at_requested_size():
    with patch.dict(os.environ, {'BRAMBLELOOP_FONT_PATH': 'isolated/font.ttf'}), \
            patch.object(charts.ImageFont, 'truetype', return_value='loaded') as load:
        assert charts._font(32) == 'loaded'
        load.assert_called_once_with('isolated/font.ttf', 32)


def test_missing_configured_and_system_fonts_remain_a_fallback():
    with patch.dict(os.environ, {'BRAMBLELOOP_FONT_PATH': 'missing.ttf'}), \
            patch.object(charts.ImageFont, 'truetype', side_effect=OSError), \
            patch.object(charts.ImageFont, 'load_default', return_value='fallback'), \
            patch.object(charts, 'FONT_FALLBACK_IN_USE', False):
        assert charts._font(32) == 'fallback'
        assert charts.FONT_FALLBACK_IN_USE is True


if __name__ == '__main__':
    for test in (test_configured_font_is_loaded_at_requested_size,
                 test_missing_configured_and_system_fonts_remain_a_fallback):
        test()
        print('OK  ', test.__name__)
    print('0 failed')
