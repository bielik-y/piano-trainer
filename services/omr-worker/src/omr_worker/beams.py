"""Ребра (вязка) восьмых и более коротких нот.

homr не распознаёт ребра: в его MusicXML нет ни одного `<beam>`, и ноты рисуются отдельно с
флажками. Группировку в оригинале мы не знаем, поэтому ноты связываются по обычным правилам
нотной записи — по долям такта:
- доля — четверть (в 2/2 — половинная, в 6/8, 9/8, 12/8 — четверть с точкой, в 2/8 и 3/8 — весь такт);
- в 4/4 полтакта из одних восьмых связывается целиком (четыре восьмые под одним ребром);
- паузы, форшлаги и ноты длиннее восьмой разрывают ребро;
- второе и следующие ребра (шестнадцатые и короче) — внутри своей группы, одиночная нота
  получает «крючок».

Ребро пишется на первую ноту аккорда. Такты, где ребра уже есть, не трогаются.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from xml.etree import ElementTree as ET

from .timing import Meter, measures_with_meter, notes_with_onsets

BEAM_LEVELS = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}
# По схеме MusicXML <beam> идёт после <staff> и перед этими элементами.
AFTER_BEAM = ("notations", "lyric", "play", "listen")


@dataclass
class Event:
    """Нота или аккорд (ребро вешается на `head`) либо пауза."""

    onset: Fraction
    duration: Fraction
    head: ET.Element
    levels: int  # сколько ребер у такой длительности; 0 — не связывается
    beams: dict[int, str] = field(default_factory=dict)

    @property
    def end(self) -> Fraction:
        return self.onset + self.duration


def add_beams(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    for measure, meter in measures_with_meter(root):
        if measure.find("note/beam") is None:
            _beam_measure(measure, meter)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _beam_measure(measure: ET.Element, meter: Meter) -> None:
    for voice in _voices(measure):
        for start, end in _spans(voice, meter):
            events = [event for event in voice if start <= event.onset < end]
            for run in _runs(events, end):
                _mark(run)
        for event in voice:
            for level, kind in sorted(event.beams.items()):
                _insert_beam(event.head, level, kind)


def _voices(measure: ET.Element) -> list[list[Event]]:
    voices: dict[tuple[str, str], list[Event]] = {}
    for onset, note in notes_with_onsets(measure):
        if note.find("grace") is not None or note.find("chord") is not None:
            continue
        key = (note.findtext("staff") or "1", note.findtext("voice") or "1")
        is_rest = note.find("rest") is not None
        voices.setdefault(key, []).append(
            Event(
                onset=onset,
                duration=Fraction(int(note.findtext("duration") or 0)),
                head=note,
                levels=0 if is_rest else BEAM_LEVELS.get(note.findtext("type") or "", 0),
            )
        )
    return list(voices.values())


def _spans(voice: list[Event], meter: Meter) -> list[tuple[Fraction, Fraction]]:
    """Отрезки такта, внутри которых ноты связываются."""
    quarter = Fraction(meter.divisions)
    if meter.beat_type == 8 and meter.beats in (6, 9, 12):
        unit = quarter * 3 / 2
    elif meter.beat_type == 8 and meter.beats <= 3:
        unit = meter.length
    elif meter.beat_type == 2:
        unit = quarter * 2
    else:
        unit = quarter
    count = max(1, int(meter.length / unit))
    spans = [(unit * i, unit * (i + 1)) for i in range(count)]

    if (meter.beats, meter.beat_type) == (4, 4):
        half = quarter * 2
        merged = []
        for start in (Fraction(0), half):
            events = [event for event in voice if start <= event.onset < start + half]
            if _only_eighths_filling(events, start, start + half):
                merged.append((start, start + half))
            else:
                merged += [(start, start + quarter), (start + quarter, start + half)]
        spans = merged
    return spans


def _only_eighths_filling(events: list[Event], start: Fraction, end: Fraction) -> bool:
    return (
        len(events) == 4
        and all(event.levels == 1 for event in events)
        and sum(event.duration for event in events) == end - start
    )


def _runs(events: list[Event], span_end: Fraction) -> list[list[Event]]:
    """Подряд идущие ноты, которые можно связать, не выходя за конец отрезка."""
    runs: list[list[Event]] = []
    current: list[Event] = []
    for event in events:
        if event.levels > 0 and event.end <= span_end:
            current.append(event)
        else:
            runs.append(current)
            current = []
    runs.append(current)
    return [run for run in runs if len(run) >= 2]


def _mark(run: list[Event]) -> None:
    for level in range(1, max(event.levels for event in run) + 1):
        index = 0
        while index < len(run):
            if run[index].levels < level:
                index += 1
                continue
            stop = index
            while stop + 1 < len(run) and run[stop + 1].levels >= level:
                stop += 1
            if level == 1 or stop > index:
                run[index].beams[level] = "begin"
                for event in run[index + 1 : stop]:
                    event.beams[level] = "continue"
                run[stop].beams[level] = "end"
            else:
                # Одиночная короткая нота — крючок в сторону соседей по группе.
                run[index].beams[level] = "forward hook" if index == 0 else "backward hook"
            index = stop + 1


def _insert_beam(note: ET.Element, level: int, kind: str) -> None:
    beam = ET.Element("beam", {"number": str(level)})
    beam.text = kind
    children = list(note)
    position = len(children)
    for index, child in enumerate(children):
        if child.tag in AFTER_BEAM:
            position = index
            break
    note.insert(position, beam)
