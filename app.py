import asyncio
import os
from collections import deque
from dotenv import load_dotenv
from typing import Annotated, AsyncGenerator, Dict, Generator, Literal, Optional, Protocol, Tuple
from dataclasses import field, dataclass
from typing_extensions import TypeAlias

from mikro_next.api.schema import Image, Stage
from arkitekt_next import easy, register, state, startup, log
from rekuest_next.declare import declare
from rekuest_next.structures.model import model
from rekuest_next.widgets import withDescription


# --- Declared remote apps ---------------------------------------------------


@declare(app="fairinogale")
class FairinoLike(Protocol):
    """The robot arm that moves slides between the pickup station, opentrons and microscope."""
    def release_at_opentrons(self, sample: str, speed: Optional[int], acceleration: Optional[int], dangerSpeed: Optional[int]) -> None:
        """Move the samples into the Opentrons."""
        ...

    def pick_up_opentrons(self, sample: str, speed: Optional[int], acceleration: Optional[int], dangerSpeed: Optional[int]) -> None:
        """Pick up the samples from the Opentrons."""
        ...

    def release_at_frame(self, sample: str, speed: Optional[int], acceleration: Optional[int], dangerSpeed: Optional[int]) -> None:
        """Move the samples onto the FRAME."""
        ...

    def pick_up_frame(self, sample: str, speed: Optional[int], acceleration: Optional[int], dangerSpeed: Optional[int]) -> None:
        """Pick up the samples from the FRAME."""
        ...

    def init_robot_and_gripper(self) -> None:
        """Initialize the robot and gripper."""
        ...

    def open_grip(self) -> None:
        """Open the gripper."""
        ...

    def close_grip(self) -> None:
        """Close the gripper."""
        ...

    def home_robot(self, move_speed: Optional[int], acceleration: Optional[int]) -> None:
        """Move the robot to the home position. ATTENTION: The robot will take the shortest path to the home position, so make sure that the way is clear, or move the arm manually to a safe position before homing."""
        ...


StageRef: TypeAlias = Stage

@declare(app="correct_coordinate_system")
class CorrectCoordinateSystemDevLike(Protocol):
    def invert_x_axis(self, stage: StageRef) -> StageRef:
        """This function takes {{stage}} and returns a new stage whose x-axis points
the other way. Every affine transformation view of the input stage is
re-attached to the new stage with its affine matrix mirrored along x
(pre-multiplied by ``diag(-1, 1, 1, 1)``), correcting the wrong-direction
x-axis of the acquisition stage."""
        ...

    def invert_y_axis(self, stage: StageRef) -> StageRef:
        """This function takes {{stage}} and returns a new stage whose y-axis points
the other way. Every affine transformation view of the input stage is
re-attached to the new stage with its affine matrix mirrored along y
(pre-multiplied by ``diag(1, -1, 1, 1)``), correcting the wrong-direction
y-axis of the acquisition stage."""
        ...

    def invert_xy_axes(self, stage: StageRef) -> StageRef:
        """This function takes {{stage}} and returns a new stage whose x- and y-axes
both point the other way. Every affine transformation view of the input
stage is re-attached to the new stage with its affine matrix mirrored along
x and y (pre-multiplied by ``diag(-1, -1, 1, 1)``), correcting both
wrong-direction axes of the acquisition stage."""
        ...


@declare(app="OT2")
class OT2Like(Protocol):
    """The Opentrons OT-2 liquid handler that runs washing and staining protocols."""

    def run_washing_protocol(self) -> None:
        """Run the washing protocol on the Opentrons."""
        ...

    def run_staining_protocol(self) -> None:
        """Run the staining protocol on the Opentrons."""
        ...

    def run_dummy_protocol(self) -> None:
        """Run a dummy protocol on the Opentrons."""
        ...


StageRef: TypeAlias = Stage
ImageRef: TypeAlias = Image

@dataclass
class PositionModel:
    x: int
    y: int
    z: int

@declare(app="FRAME Fork Approval")
class FrameLike(Protocol):
#     async def runTileScan(self, center_x_micrometer: Optional[float], center_y_micrometer: Optional[float], range_x_micrometer: Optional[int], range_y_micrometer: Optional[int], step_x_micrometer: Optional[float], step_y_micrometer: Optional[float], overlap_percent: Optional[float], illumination_channel: Optional[str], illumination_intensity: Optional[int], exposure_time: Optional[float], gain: Optional[float], speed: Optional[int], positionerName: Optional[str], performAutofocus: Optional[bool], autofocus_range: Optional[int], autofocus_resolution: Optional[int], autofocus_illumination_channel: Optional[str], objective_id: Optional[int], t_settle: Optional[float]) -> StageRef:
#         """Runs a tile scan by moving the specified positioner in a grid pattern centered
# at the given coordinates, capturing images at each position with specified
# illumination and camera settings, and yielding the images with appropriate
# affine transformations for stitching.

# The step size is automatically calculated based on the current objective's
# field of view and the specified overlap percentage, unless explicitly provided."""
#         ...

#     async def goToPosition(self, x_micrometer: float, y_micrometer: float, positionerName: Optional[str], speed: Optional[int], is_blocking: Optional[bool], t_settle: Optional[float]) -> None:
#         """Moves the specified positioner (or the first available one) to the given
# X and Y coordinates in micrometers."""
#         ...

    # async def acquireFrame(self, frameSync: Optional[int]) -> StageRef:
    #     """Acquire a single frame from the detector."""
    #     ...

    # async def getStagePosition(self, positionerName: Optional[str]) -> PositionModel:
    #     """Get current stage position."""
    #     ...

    def homeStageAxis(self, positionerName: Optional[str], axis: Optional[str], is_blocking: Optional[bool]) -> None:
        """Home stage axis."""
        ...

    # async def setLaserState(self, laserName: str, isActive: bool, value: Optional[int]) -> None:
    #     """Set laser state."""
    #     ...

    # async def moveStage(self, positionerName: Optional[str], axis: Optional[str], distance: Optional[int], is_absolute: Optional[bool], is_blocking: Optional[bool], speed: Optional[int]) -> None:
    #     """Move stage."""
        ...

    # async def moveToSampleLoadingPosition(self, speed: Optional[int], is_blocking: Optional[bool]) -> None:
    #     """Move to sample loading position."""
    #     ...

    def saveFirstWellCorner(self, positionerName: Optional[str]) -> PositionModel:
        """Save current stage XY position as first corner of a well rectangle."""
        ...

    def saveSecondWellCorner(self, well_id: str, plate_type: Optional[str], positionerName: Optional[str]) -> None:
        """Save current stage XY position as second corner and commit the well bounds."""
        ...

    def previewWell(self, well_id: Optional[str], plate_type: Optional[str], perform_autofocus: Optional[bool], autofocus_range: Optional[int], autofocus_resolution: Optional[int], speed: Optional[int], t_settle: Optional[float], positionerName: Optional[str]) -> ImageRef:
        """Move to a well center, run autofocus, and capture one frame."""
        ...
    
    def run_well_tile_scan(self, well_id: Optional[str], plate_type: Optional[str], illumination_channel: Optional[str], illumination_intensity: Optional[float], exposure_time: Optional[float], gain: Optional[float], overlap_percent: Optional[float], focus_map_grid_rows: Optional[int], focus_map_grid_cols: Optional[int], autofocus_range: Optional[int], autofocus_resolution: Optional[int], objective_id: Optional[int], speed: Optional[int], t_settle: Optional[float], positionerName: Optional[str]) -> Stage:
        """Scan an entire well with focus mapping."""
        ...


@declare(app="stainstorm-stitch")
class StitchLike(Protocol):
    def generate_n_string(self, n: Optional[int], timeout: Optional[int]) -> str:
        """This function generates {{n}} strings with a {{timeout}} ms timeout
between each string."""
        ...

    def append_world(self, hello: str) -> str:
        """Appends the string ' World' to the input."""
        ...

    def print_string(self, input: str) -> str:
        """Prints the input string to the console."""
        ...

    def stitch_stage(self, stage: StageRef, name: Optional[str], do_shading: Optional[bool], hp_sigma: Optional[float], ncc_seam_tol_px: Optional[int], ncc_ortho_px: Optional[int], assumed_overlap_frac: Optional[float], flip_x: Optional[bool], flip_y: Optional[bool], do_landmark_refine: Optional[bool], landmark_n_keypoints: Optional[int], landmark_min_matches: Optional[int], blending_width_nm: Optional[float]) -> ImageRef:
        """Pulls every tile attached to the Stage (via its AffineTransformationViews),
reads the per-tile stage origin and pixel scale from each view's affine
matrix, then runs:

  1. BaSiC shading correction (optional, on by default)
  2. HP-filtered normalised cross-correlation around the assumed step
     (window = `+/- ncc_seam_tol_px` along the seam axis,
     `+/- ncc_ortho_px` orthogonal). Sub-pixel via parabolic peak
     interpolation.
  3. Least-squares solve for per-tile (y, x) offsets from the pair shifts.
  4. Optional landmark refinement (ORB feature matching in each pair's
     overlap region) + a second LSQ.
  5. multiview-stitcher fuse with weighted-average blending.

The fused mosaic is persisted as a new Image (with an
AffineTransformationView placing it back in the same Stage) and returned."""
        ...

    def dump_stage_tiles(self, stage: StageRef, output_dir: Optional[str]) -> str:
        """convention so the existing stitching notebooks can run on the dump
directly.

Filename pattern: `t<YYYYMMDD>_<HHMMSS>_x<x_nm>_y<y_nm>_z<z_nm>_c0_mikro_
i<N>_p<image_id>.tif` -- `_x..._y..._z...` are the integer nanometre
translations from the AffineTransformationView, `iNNNN` is a 4-digit
enumeration of the tiles (sorted by y_nm then x_nm), `pNNN` is the
short image id.

The output folder is created next to where the worker is running.
Open the existing `stitching.ipynb` and change `DATA_DIR` to that
folder to run the same pipeline + diagnostics on the new tiles."""
        ...


FileRef: TypeAlias = str

@declare(app="cellpose-ARK")
class SegmenterLike(Protocol):
    def run_cellpose_SAM(self, image: ImageRef, pretrained_model: Optional[FileRef], gpu: Optional[bool], diameter: Optional[float], flow_threshold: Optional[float], cellprob_threshold: Optional[float], tile_norm_blocksize: Optional[int], min_size: Optional[int]) -> Tuple[ImageRef, ImageRef, ImageRef]:
        """diameter: expected cell diameter in PIXELS. Cellpose-SAM was trained on
    ROIs of 7.5-120 px (mean 30 px) and is largely size-invariant, so 0
    (=auto) is fine for most data. Set it only if your cells fall outside
    that range. Cellpose works in pixels, not physical units: if you know
    the pixel size, compute diameter_px = cell_size_nm / pixel_size_nm.
flow_threshold: max flow error per mask (default 0.4). Increase to keep
    more ROIs, decrease to drop ill-shaped ones.
cellprob_threshold: pixels above this are used for masks (default 0.0,
    range ~-6..+6). Decrease to recover cells missed in dim areas;
    increase to suppress spurious masks in empty/background areas.
tile_norm_blocksize: 0 = global normalization. Set to a window size in
    pixels (e.g. 100-200) to normalize in tiles, which brightens dark
    regions so cells in unevenly-illuminated areas are not missed.
min_size: ROIs smaller than this many pixels are discarded (default 15)."""
        ...


# --- Structured input model -------------------------------------------------


@model
class Slide:
    name: Annotated[str, withDescription("Display name of the slide.")]
    protocol: Annotated[
        str,
        withDescription("The Opentrons protocol to run for this slide."),
    ]


# --- Local app state --------------------------------------------------------


class SlideStatus:
    """The stages a slide moves through during the concurrent staining workflow."""

    QUEUED = "queued"
    IMAGING = "imaging"
    ANALYZING = "analyzing"
    STAINING = "staining"
    DONE = "done"


@state
class AppState:
    currently_imaging_slide: Annotated[
        Optional[str],
        withDescription("The name of the slide currently being imaged."),
    ] = None
    slide_status: Annotated[
        Dict[str, str],
        withDescription("The current workflow status per slide name (see SlideStatus)."),
    ] = field(default_factory=dict)
    staining_rounds: Annotated[
        Dict[str, int],
        withDescription("The number of completed staining rounds per slide name."),
    ] = field(default_factory=dict)
    latest_images: Annotated[
        Dict[str, Image],
        withDescription("The latest stitched composite per slide name."),
    ] = field(default_factory=dict)
    latest_segmented: Annotated[
        Dict[str, Image],
        withDescription("The latest segmentation mask per slide name."),
    ] = field(default_factory=dict)


@startup
def startup_hook() -> AppState:
    """Initialize the app state when the agent boots."""
    return AppState()


# --- Helpers ----------------------------------------------------------------


def _run_protocol(
    opentrons: OT2Like, protocol: Literal["washing", "staining"]
) -> None:
    """Dispatch to the correct Opentrons protocol function."""
    if protocol == "washing":
        opentrons.run_washing_protocol()
    elif protocol == 'staining':
        opentrons.run_staining_protocol()
    else:
        opentrons.run_dummy_protocol()


# --- Registered protocols ---------------------------------------------------


@register
def run_stainstorm_7(
    robot: FairinoLike,
    opentrons: OT2Like,
    microscope: FrameLike,
    segmenter: SegmenterLike,
    coordinate_corrector: CorrectCoordinateSystemDevLike,
    loaded_slides: list[Slide],
    max_iterations: int = 5,
) -> Generator[Stage, None, None]:
    """Iteratively image, stitch, segment, and stain each slide.
    """

    for slide in loaded_slides:
        microscope.homeStageAxis()
        robot.init_robot_and_gripper()
        robot.pick_up_opentrons(slide.name)
        robot.release_at_frame(slide.name)

        frame1_before = microscope.run_well_tile_scan(well_id="A1")
        yield frame1_before
        # frame2_before = microscope.run_well_tile_scan(well_id="A2")
        # yield frame2_before
        frame1_before = coordinate_corrector.invert_x_axis(frame1_before)
        cells_before, _, _ = segmenter.run_cellpose_SAM(frame1_before, diameter=13, gpu=True)
        yield cells_before
        # frame2_before = coordinate_corrector.invert_x_axis(frame2_before)
        # cells2_before, _, _ = segmenter.run_cellpose_SAM(frame2_before)
        # yield cells2_before

        for iteration in range(max_iterations):
            microscope.homeStageAxis()
            robot.pick_up_frame(slide.name)
            robot.release_at_opentrons(slide.name)
            _run_protocol(opentrons, slide.protocol)
            robot.pick_up_opentrons(slide.name)
            robot.release_at_frame(slide.name)

            frame1_after = microscope.run_well_tile_scan(well_id="A1")
            yield frame1_after
            # frame2_after = microscope.run_well_tile_scan(well_id="A2")
            # yield frame2_after
            frame1_after = coordinate_corrector.invert_x_axis(frame1_after)
            cells1_after, _, _ = segmenter.run_cellpose_SAM(frame1_after, diameter=13, gpu=True)
            yield cells1_after
            # frame2_after = coordinate_corrector.invert_x_axis(frame2_after)
            # cells2_after, _, _ = segmenter.run_cellpose_SAM(frame2_after)
            # yield cells2_after

            log(f"Iteration {iteration + 1} complete.")

        robot.pick_up_frame(slide.name)


# @register
# def run_concurrent_staining_6(
#     robot: FairinoLike,
#     opentrons: OT2Like,
#     microscope: FrameLike,
#     stitcher: StitchLike,
#     segmenter: SegmenterLike,
#     # analyzer: AnalyzerLike,
#     state: AppState,
#     loaded_slides: list[Slide],
#     target_stain_percentage: float = 0.8,
#     max_rounds: int = 5,
# ) -> AsyncGenerator[Image, None]:
#     """Concurrent staining workflow with an internal task-tracking scheduler.

#     The robot and single microscope are a serial bottleneck, so only one slide is
#     ever physically handled at a time. The expensive compute -- stitching the tile
#     grid, Cellpose segmentation, stain quantification -- is independent per slide
#     and is fired off as a background ``asyncio`` task the moment a slide's tiles
#     are acquired. While those tasks run on the agent fleet, the robot keeps moving
#     the next slide.

#     The loop below keeps track of the in-flight compute tasks. As each analysis
#     finishes we check whether the slide is *under*-stained (too few stained cells,
#     ``percentage < target_stain_percentage``). If so the slide is queued for a
#     staining run on the Opentrons and then re-imaged, up to ``max_rounds`` times.

#     Every transition is mirrored into the published ``AppState`` so observers can
#     follow each slide moving through queued -> imaging -> analyzing -> staining ->
#     done, along with its staining-round count and latest stitched/segmented images.
#     """

#     rounds: dict[str, int] = {slide.name: 0 for slide in loaded_slides}
#     for slide in loaded_slides:
#         state.slide_status[slide.name] = SlideStatus.QUEUED
#         state.staining_rounds[slide.name] = 0

#     # Serial physical work queue: ("image", slide) or ("stain", slide).
#     physical: deque[tuple[str, Slide]] = deque(
#         ("image", slide) for slide in loaded_slides
#     )
#     # In-flight stitch -> segment -> analyze tasks, keyed to their slide.
#     compute: dict[asyncio.Task[tuple[Image, Image, float]], Slide] = {}

#     async def analyze(stage: StageRef) -> tuple[Image, Image, float]:
#         """Offloaded compute: stitch the tiles, segment with Cellpose, measure stain."""
#         stitched = await stitcher.stitch_stage(stage)
#         cells, _, _ = await segmenter.run_cellpose_SAM(stitched)
#         # percentage = await analyzer.calculate_stain_percentage(cells)
#         return stitched, cells, 60

#     async def image_slide(slide: Slide) -> None:
#         """Serial physical op: place slide on frame, run tile scan, pick it back up."""
#         state.currently_imaging_slide = slide.name
#         state.slide_status[slide.name] = SlideStatus.IMAGING
#         await robot.release_at_frame(slide.name)
#         stage = await microscope.run_well_tileScan(well_id=slide.well_id)
#         await robot.pick_up_frame(slide.name)
#         state.currently_imaging_slide = None
#         state.slide_status[slide.name] = SlideStatus.ANALYZING
#         compute[asyncio.ensure_future(analyze(stage))] = slide

#     async def stain_slide(slide: Slide) -> None:
#         """Serial physical op: carry the slide to the Opentrons and stain it."""
#         state.slide_status[slide.name] = SlideStatus.STAINING
#         await robot.release_at_opentrons(slide.name)
#         await _run_protocol(opentrons, slide.protocol)
#         await robot.pick_up_opentrons(slide.name)

#     while physical or compute:
#         # 1. Harvest any compute that has finished and decide on more staining.
#         for task in [t for t in compute if t.done()]:
#             slide = compute.pop(task)
#             stitched, segmented, percentage = task.result()
#             state.latest_images[slide.name] = stitched
#             state.latest_segmented[slide.name] = segmented
#             yield stitched
#             yield segmented

#             if percentage < target_stain_percentage and rounds[slide.name] < max_rounds:
#                 rounds[slide.name] += 1
#                 state.staining_rounds[slide.name] = rounds[slide.name]
#                 log(
#                     f"Slide {slide.name}: {percentage:.2%} stained -- staining "
#                     f"(round {rounds[slide.name]})."
#                 )
#                 physical.append(("stain", slide))
#             else:
#                 state.slide_status[slide.name] = SlideStatus.DONE
#                 log(f"Slide {slide.name}: {percentage:.2%} stained -- done.")

#         # 2. Run a single physical operation if one is queued; the hardware is
#         #    serial so we only ever do one at a time, keeping the compute fleet
#         #    busy in the background.
#         if physical:
#             op, slide = physical.popleft()
#             if op == "image":
#                 image_slide(slide)
#             else:
#                 stain_slide(slide)
#                 physical.append(("image", slide))  # re-image after staining
#         elif compute:
#             # Nothing physical to do right now -- wait for the next analysis.
#             asyncio.wait(set(compute), return_when=asyncio.FIRST_COMPLETED)


if __name__ == "__main__":
    load_dotenv()  # Load environment variables from .env file
    redeem_token = os.getenv("REDEEM_TOKEN", None)
    with easy(identifier="stainstorm", redeem_token=redeem_token) as app:
        app.run()
