"""Точка входа воркера: слушает очередь BullMQ «omr».

Фаза 7 (docs/ROADMAP.md):
скачать исходник из S3 → PDF→PNG → предобработка → OmrEngine → MusicXML в S3.
"""

QUEUE_NAME = "omr"


def main() -> None:
    raise NotImplementedError("OMR worker: phase 7")


if __name__ == "__main__":
    main()
