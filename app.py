from mikro_next.api.schema import (
    Image,
    from_array_like,
    PartialInstanceMaskViewInput,
    create_reference_view,
)
from arkitekt_next import register
import numpy as np


@register
def move_robot_slide_holder():
    # Implement robot movement logic here
    print("Moving robot slide holder")
    return


@register
def pick_up_slide_in_tray(slider: int):
    # Implement robot movement logic here
    print(f"Picking up slide {slider} in tray")
    return


@register
def drop_slider_in_tray(slider: int):
    # Implement robot movement logic here
    print(f"Dropping slide {slider} in tray")
    # Implement robot movement logic here
    return


@register
def move_robot_to_microscope():
    # Implement robot movement logic here
    print("Moving robot to microscope")
    return


@register
def segment_cells(image: Image) -> Image:
    # Implement cell segmentation logic here
    return from_array_like(
        image.data > 0,
        name="Segmentation of the image",
        instance_mask_views=[
            PartialInstanceMaskViewInput(
                referenceView=create_reference_view(image),
            )
        ],
    )


@register
def calculate_percentage_of_stained_cells(image: Image) -> float:
    # Implement percentage calculation logic here
    return np.random.rand()


@register
def move_robot_to_opentrons():
    # Implement robot movement logic here
    print("Moving robot to Opentrons")
    return


@register
def drop_slide():
    # Implement robot movement logic here
    print("Dropping slide")
    return


@register
def pickup_slide():
    # Implement robot movement logic here
    print("Picking up slide")
    return


@register
def acquire_image() -> Image:
    # Implement image acquisition logic here
    print("Acquiring image")
    return from_array_like(
        np.random.randint(0, 256, (1, 100, 100), dtype=np.uint8), name="Acquired Image"
    )


@register
def run_staining_protocol():
    # Implement staining protocol logic here
    print("Running staining protocol")
    return


@register
def smart_logic_loop(protocol: str, iteration=0, max_iterations=5):
    image = acquire_image()
    segmented_image = segment_cells(image)
    percentage = calculate_percentage_of_stained_cells(segmented_image)

    if percentage < 0.8 and iteration < max_iterations:
        pickup_slide()
        move_robot_to_opentrons()
        drop_slide()

        run_staining_protocol()

        pickup_slide()
        move_robot_to_microscope()
        drop_slide()

        smart_logic_loop(protocol, iteration + 1)

    return


@register
def the_loop():
    sliders = []
    protocols = ["anti-CD31", "anti-Podoplanin"]

    for i in range(5):
        sliders.append(i)

    move_robot_slide_holder()
    for slider in sliders:
        pick_up_slide_in_tray(slider)

        move_robot_to_microscope()
        drop_slide()

        for protocol in protocols:
            print(f"Running protocol: {protocol}")
            smart_logic_loop(protocol)

        move_robot_slide_holder()
        drop_slider_in_tray(slider)

    return sliders
