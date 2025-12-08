import os
from typing import Generator
from kraph.api.schema import (
    EntityRoleDefinitionInput,
    MetricKind,
    VariableDefinitionInput,
    create_entity_category,
    create_graph,
    create_measurement_category,
    create_protocol_event_category,
    create_structure_metric,
)
from mikro_next.api.schema import Image
from arkitekt_next import easy, protocol, log, register, find
import numpy as np
from dotenv import load_dotenv

# Not that everything is a stub and needs to be implemented with real logic
# by other apps or humans, we use standard python function and the ellipsis
# (...) to indicate that the function is not implemented here.

# when using the @protocol decorator, all functions are filtered that have the same
# output and input types, so that they can be replaced by other implementations
# in the future this will be more fine grained, e.g by passing which collections
# the function should use to find implementations
# e.g. @protocol(collections=["segmentation"])

PERCENTAGE_OF_STAINED_CELLS_THRESHOLD = 10 # 10% of stained cells
STAIN_THRESHOLD = 500 # eyeballed threshold from one image

## ARKIRINO
@protocol
def pickup_slide_from_pickupstation(speed=100, acceleration=100):
    "A function to pickup a slide from the pickup station"
    ...

@protocol
def move_slide_to_opentron(speed=100, acceleration=100):
    "A function to move a slide to the opentron"
    ...

@protocol
def pickup_slide_from_opentron(speed=100, acceleration=100):
    "A function to pickup a slide from the opentron"
    ...

@protocol
def move_slide_to_microscope(speed=100, acceleration=100):
    "A function to move a slide to the microscope"
    ...

@protocol
def pickup_slide_from_microscope(speed=100, acceleration=100):
    "A function to pickup a slide from the microscope"
    ...

@protocol
def move_slide_to_pickupstation(speed=100, acceleration=100):
    "A function to move a slide to the pickup station"
    ...

@protocol
def shutdown_robot_arm():
    "A function to shutdown the robot arm"
    ...

## ImSwitch (Microscope)
@protocol
def runTileScan(
    center_x_micrometer: float | None = None,
    center_y_micrometer: float | None = None,
    range_x_micrometer: float = 5000,
    range_y_micrometer: float = 5000,
    step_x_micrometer: float | None = None,
    step_y_micrometer: float | None = None,
    overlap_percent: float = 10.0,
    illumination_channel: str | None = "LED",
    illumination_intensity: float = 1024,
    exposure_time: float | None = None,
    gain: float | None = None,
    speed: float = 10000,
    positionerName: str | None = None,
    performAutofocus: bool = False,
    autofocus_range: float = 100,
    autofocus_resolution: float = 10,
    autofocus_illumination_channel: str | None = None,
    objective_id: int | None = None,
    t_settle: float = 0.2,
) -> Generator[Image, None, None]:
    """Run a tile scan with enhanced control over imaging parameters.

    Runs a tile scan by moving the specified positioner in a grid pattern centered
    at the given coordinates, capturing images at each position with specified
    illumination and camera settings, and yielding the images with appropriate
    affine transformations for stitching.

    The step size is automatically calculated based on the current objective's
    field of view and the specified overlap percentage, unless explicitly provided.

    Args:
        center_x_micrometer (float | None): Center position in the X direction (micrometers).
            If None, uses current X position.
        center_y_micrometer (float | None): Center position in the Y direction (micrometers).
            If None, uses current Y position.
        range_x_micrometer (float): Total range to scan in the X direction (micrometers).
        range_y_micrometer (float): Total range to scan in the Y direction (micrometers).
        step_x_micrometer (float | None): Step size in the X direction (micrometers).
            If None, automatically calculated based on objective FOV and overlap.
        step_y_micrometer (float | None): Step size in the Y direction (micrometers).
            If None, automatically calculated based on objective FOV and overlap.
        overlap_percent (float): Percentage of overlap between adjacent tiles (0-100).
            Only used if step_x/y_micrometer are None. Default is 10%.
        illumination_channel (str | None): Name of the illumination source to use.
            If None, uses current illumination settings.
        illumination_intensity (float): Intensity value for the illumination source (0-100).
        exposure_time (float | None): Exposure time in milliseconds. If None, uses current setting.
        gain (float | None): Camera gain value. If None, uses current setting.
        speed (float): Speed of the positioner movement (units per second).
        positionerName (str | None): Name of the positioner to use. If None,
            the first available positioner will be used.
        performAutofocus (bool): Whether to perform autofocus at each tile position.
        autofocus_range (float): Range for autofocus scan in Z direction (micrometers).
        autofocus_resolution (float): Step size for autofocus scan (micrometers).
        autofocus_illumination_channel (str | None): Illumination channel to use for autofocus.
            If None, uses the same as illumination_channel.
        objective_id (int | None): ID of the objective to use (0 or 1).
            If specified, the objective will be moved to this position before scanning
            and magnification will be retrieved from ObjectiveManager. If None, uses current objective.
        t_settle (float): Time to wait after moving for the system to settle, in seconds.

    Yields:
        Image: Captured image with affine transformation for stitching.
    """
    ...


## StarMist
@protocol
def predict_stardist_he(image: Image) -> Image:
    """Segment HE

    Segments Cells using the stardist he pretrained model

    Args:
        image (Image): The Input Image (needs to have at least 3 channels).
    Returns:
        Image: An Image with the Segmented Cells.

    """
    ...


## OT2 (OpenTrons)
@protocol
def run_washing_protocol():
    "A function to run the washing protocol on the OpenTrons"
    ...

# For now we just run one cycle with washing a pre-stained slide and check the washing efficiency
# @register
# def run_staining_protocol():
#     "A function to run the IHC staining protocol"
#     ...

## Image analysis (one app)
@protocol
def residual_stain_quantity(image: Image, stain_threshold: int = 500) -> float:
    "A function to estime the residual stain quantity in the second channel of a 2 channel IHC image"
    ...

@protocol
def count_segmented_cells(image: Image) -> int:
    "A function to count the number of segmented cells in a segmentation mask"
    ...

@protocol
def rgb_to_ihc_image(image: Image) -> Image:
    "A function to deconvolve stains on a RGB image to a 2 channel IHC image. H+AEC stain assumed."
    ...

# depencies must be listed in this array to ensure they are available
# when this function is called (will appear in the UI)
@register(
    dependencies=[
        pickup_slide_from_pickupstation,
        move_slide_to_opentron,
        pickup_slide_from_opentron,
        move_slide_to_microscope,
        pickup_slide_from_microscope,
        move_slide_to_pickupstation,
        shutdown_robot_arm,
        runTileScan,
        predict_stardist_he,
        residual_stain_quantity,
        count_segmented_cells,
        rgb_to_ihc_image,
        run_washing_protocol
    ]
)
def smart_logic_loop(max_iterations=2):
    num_sliders = 1 # FOR NOW ONLY ONE SLIDER IS SUPPORTED

    for slider in range(num_sliders):
        assert slider == 0, "FOR NOW ONLY ONE SLIDER IS SUPPORTED"
        pickup_slide_from_pickupstation()
        move_slide_to_microscope()

        # Run initial acquisition and segmentation

        stain_levels = []
        for tile in runTileScan(exposure_time=100, illumination_intensity=100, gain=2):
            segmented_image = predict_stardist_he(tile)
            num_cells = count_segmented_cells(segmented_image)
            if num_cells < 10:
                continue
            ihc_image = rgb_to_ihc_image(tile)  
            stain_level = residual_stain_quantity(ihc_image)
            stain_levels.append(stain_level)
        pre_wash_avg_stain_level = np.mean(stain_levels)
        log(f"TileScan stain Levels: {stain_levels}, Pre-wash avg stain level: {pre_wash_avg_stain_level}")

        iteration = 0
        current_avg_stain_level = pre_wash_avg_stain_level
        while (
            current_avg_stain_level > PERCENTAGE_OF_STAINED_CELLS_THRESHOLD
            and iteration < max_iterations
        ):
            pickup_slide_from_microscope()
            move_slide_to_opentron()

            run_washing_protocol()

            pickup_slide_from_opentron()
            move_slide_to_microscope()

            stain_levels = []
            for tile in runTileScan(exposure_time=100, illumination_intensity=100, gain=2):
                segmented_image = predict_stardist_he(tile)
                num_cells = count_segmented_cells(segmented_image)
                if num_cells < 10:
                    continue
                ihc_image = rgb_to_ihc_image(tile)  
                stain_level = residual_stain_quantity(ihc_image, stain_threshold=STAIN_THRESHOLD)
                stain_levels.append(stain_level)
            current_avg_stain_level = np.mean(stain_levels)
            log(
                f"TileScan stain Levels: {stain_levels}, Iteration {iteration} after wash avg stain level: {current_avg_stain_level}"
            )
            iteration += 1
        if iteration == max_iterations:
            log("Reached maximum iterations without sufficient staining.")
        else:
            log(f"Iteration {iteration} after wash avg stain level: {current_avg_stain_level} was sufficient.\n Washing successful.")

        pickup_slide_from_microscope()
        move_slide_to_pickupstation()
    log("All sliders processed. Finished stainSTORMING smart workflow! \n Shutting down necessarydevices.")
    shutdown_robot_arm()
    return


if __name__ == "__main__":
    load_dotenv()
    app_name = os.getenv("ARKITEKT_APPNAME", "")
    if app_name == "":
        print(
            "ARKITEKT_APPNAME is not set. Please set the ARKITEKT_APPNAME environment variable. For example put it in .env file."
        )
        exit(1)
    app_url = os.getenv("ARKITEKT_URL", "go.arkitekt.live")
    app = easy(identifier=app_name, url=app_url, redeem_token=os.getenv("REDEEM_TOKEN"))
    app.enter()
    app.run()
