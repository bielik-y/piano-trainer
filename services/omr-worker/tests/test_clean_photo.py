from pathlib import Path

import cv2
import numpy as np

from omr_worker.preprocess import clean_photo


def make_photo(path: Path) -> None:
    """Бумага с тенью слева, сверху бледные линии (просвечивание), ниже — чёткий нотоносец."""
    width, height = 2400, 2000
    shade = np.linspace(150, 235, width, dtype=np.float32)  # тень слева, светлее справа
    image = np.tile(shade, (height, 1))
    for y in range(100, 200, 20):  # просвечивание: на 12 % темнее бумаги
        image[y : y + 3] *= 0.88
    for y in range(400, 500, 20):  # печать: почти чёрные линии по всей ширине, и в тени тоже
        image[y : y + 3] = 40
    cv2.imwrite(str(path), image.astype(np.uint8))


def test_photo_loses_shadow_and_show_through(tmp_path: Path):
    path = tmp_path / "1.png"
    make_photo(path)
    clean_photo(path)
    result = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

    # Бумага ровно-белая и в тени, и на свету.
    assert result[300, 50] == 255 and result[300, 2350] == 255
    # Просвечивающие линии исчезли.
    assert result[100:200].min() == 255
    # Линии печати остались тёмными по всей ширине.
    for y in range(400, 500, 20):
        assert result[y + 1, 50] < 128 and result[y + 1, 2350] < 128


def test_small_photo_keeps_pale_lines(tmp_path: Path):
    # Снимок, сжатый мессенджером: линии нотоносца бледные, порог их бы порвал.
    path = tmp_path / "1.png"
    image = np.full((1280, 960), 200, dtype=np.uint8)
    image[400:401] = 160  # линия в пиксель, на 20 % темнее бумаги
    cv2.imwrite(str(path), image)
    clean_photo(path)
    result = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert result[400, 500] < result[300, 500]
