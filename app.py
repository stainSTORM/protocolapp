from mikro_next.api.schema import Image


def calculate_max(image: Image) -> int:
    return image.data.max()
