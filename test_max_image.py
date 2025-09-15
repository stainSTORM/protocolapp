from app import segment_cells, the_loop
from mikro_next.api.schema import from_array_like
import numpy as np
from arkitekt_next.pytest import EasyApp


def test_calculate_segmented_cells(test_app: EasyApp):
    image = from_array_like(np.zeros((1, 1000, 1000)), name="test_image")
    assert segment_cells(image).data.max() == 0


def run_loop(test_app: EasyApp):
    result = the_loop.call(test_app)
    assert result == [0, 1, 2, 3, 4]
