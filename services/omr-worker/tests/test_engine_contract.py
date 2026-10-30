from omr_worker.engines.base import OmrResult


def test_result_is_constructible():
    result = OmrResult(music_xml="<score-partwise/>")
    assert result.music_xml.startswith("<score-partwise")
