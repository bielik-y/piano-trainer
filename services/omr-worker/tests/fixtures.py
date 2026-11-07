"""Синтетический MusicXML в формате homr: одна партия, два нотоносца."""


def measure(number: int, rh: list[tuple[str, int]], lh: list[tuple[str, int]],
            time: str | None = None) -> str:
    """rh/lh — список (высота вида 'C4' или 'rest', длительность в шестнадцатых); divisions = 4."""
    attrs = ""
    if time:
        beats, beat_type = time.split("/")
        attrs = (
            "<attributes><divisions>4</divisions><key><fifths>0</fifths></key>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            "<staves>2</staves><clef number=\"1\"><sign>G</sign><line>2</line></clef>"
            "<clef number=\"2\"><sign>F</sign><line>4</line></clef></attributes>"
        )
    total_rh = sum(d for _, d in rh)
    body = _notes(rh, staff=1, voice=1)
    if lh:
        body += f"<backup><duration>{total_rh}</duration></backup>" + _notes(lh, staff=2, voice=5)
    return f'<measure number="{number}">{attrs}{body}</measure>'


def _notes(notes: list[tuple[str, int]], staff: int, voice: int) -> str:
    out = []
    types = {1: "16th", 2: "eighth", 4: "quarter", 8: "half", 16: "whole"}
    for pitch, duration in notes:
        if pitch == "rest":
            head = "<rest/>"
        else:
            head = f"<pitch><step>{pitch[0]}</step><octave>{pitch[1]}</octave></pitch>"
        out.append(
            f"<note>{head}<duration>{duration}</duration><voice>{voice}</voice>"
            f"<type>{types.get(duration, 'quarter')}</type><staff>{staff}</staff></note>"
        )
    return "".join(out)


def score(*measures: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>'
        f'<part id="P1">{"".join(measures)}</part></score-partwise>'
    )


def good_measure(number: int, time: str | None = None) -> str:
    return measure(number, [("C5", 8), ("E5", 8)], [("C3", 16)], time=time)


def bad_measure(number: int) -> str:
    # Правая рука — 5 четвертей вместо 4 (короче можно последнему такту пьесы, длиннее — никому).
    return measure(number, [("C5", 4), ("D5", 4), ("E5", 4), ("F5", 4), ("G5", 4)], [("C3", 16)])
