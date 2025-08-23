from app import calculate_max
from mikro_next.api.schema import from_array_like
import numpy as np
from arkitekt_next.pytest import EasyApp


def test_calculate_max(test_app: EasyApp):
    image = from_array_like(np.zeros((1, 100, 100)), name="test_image")
    assert calculate_max(image) == 0
