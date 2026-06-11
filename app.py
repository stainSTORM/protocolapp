import asyncio
import os
from collections import deque
from dotenv import load_dotenv
from typing import Annotated, AsyncGenerator, Dict, Literal, Optional, Protocol
from dataclasses import field

from mikro_next.api.schema import Image
from arkitekt_next import easy, register, state, startup, log
from rekuest_next.declare import declare
from rekuest_next.structures.model import model
from rekuest_next.widgets import withDescription


# --- Declared remote apps ---------------------------------------------------

@declare(app="fairinogale")
class FarinoLike(Protocol):
    """The robot arm that moves slides between the pickup station, opentrons and microscope."""

    async def pickup_slide_from_pickupstation(self) -> None:
        """Pick up a slide from the pickup/tray station."""
        ...

    async def move_slide_to_opentron(self) -> None:
        """Place the currently held slide onto the Opentrons deck."""
        ...

    async def pickup_slide_from_opentron(self) -> None:
        """Pick up the slide from the Opentrons deck."""
        ...

    async def move_slide_to_microscope(self) -> None:
        """Place the currently held slide onto the microscope stage."""
        ...

    async def pickup_slide_from_microscope(self) -> None:
        """Pick up the slide from the microscope stage."""
        ...

    async def move_slide_to_pickupstation(self) -> None:
        """Return the currently held slide to the pickup/tray station."""
        ...


@declare(app="OT2")
class OT2Like(Protocol):
    """The Opentrons OT-2 liquid handler that runs washing and staining protocols."""

    async def run_washing_protocol(self) -> None:
        """Run the washing protocol on the Opentrons."""
        ...

    async def run_staining_protocol(self) -> None:
        """Run the staining protocol on the Opentrons."""
        ...


@declare(app="frame", min=1, max=1)
class FrameLike(Protocol):
    """The microscope that acquires images of a sample."""

    async def acquire_image(self) -> Image:
        """Acquire an image from the microscope sensor."""
        ...

    async def move_to_position(self, position: str) -> None:
        """Move the stage to a named position."""
        ...


@declare(app="stitcher", min=1, max=10)
class StitcherLike(Protocol):
    """A stitching app that fuses overlapping tile images into one composite."""

    async def stitch_images(self, images: list[Image]) -> Image:
        """Stitch a list of overlapping tile images into a single composite image."""
        ...


@declare(app="cellpose", min=2, max=10)
class SegmenterLike(Protocol):
    """A Cellpose segmentation app that labels cells in an image."""

    async def segment_image(self, image: Image) -> Image:
        """Segment an image with Cellpose, returning a label mask of cells."""
        ...


@declare(app="analyzer")
class AnalyzerLike(Protocol):
    """An analysis app that quantifies staining from a segmentation mask."""

    async def calculate_stain_percentage(self, image: Image) -> float:
        """Calculate the percentage of stained cells from a label mask."""
        ...


# --- Structured input model -------------------------------------------------


@model
class Slide:
    name: Annotated[str, withDescription("Display name of the slide.")]
    protocol: Annotated[
        Literal["washing", "staining"],
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
async def startup_hook() -> AppState:
    """Initialize the app state when the agent boots."""
    return AppState()


# --- Helpers ----------------------------------------------------------------


async def _run_protocol(
    opentrons: OT2Like, protocol: Literal["washing", "staining"]
) -> None:
    """Dispatch to the correct Opentrons protocol function."""
    if protocol == "washing":
        await opentrons.run_washing_protocol()
    else:
        await opentrons.run_staining_protocol()


async def _scan_tiles(
    microscope: FrameLike, tile_positions: list[str]
) -> list[Image]:
    """Acquire one image per tile position (serial — a single physical stage)."""
    tiles: list[Image] = []
    for position in tile_positions:
        await microscope.move_to_position(position)
        tiles.append(await microscope.acquire_image())
    return tiles


# --- Registered protocols ---------------------------------------------------


@register
async def run_stainstorm(
    robot: FarinoLike,
    opentrons: OT2Like,
    microscope: FrameLike,
    segmenter: SegmenterLike,
    analyzer: AnalyzerLike,
    loaded_slides: list[Slide],
    max_iterations: int = 5,
) -> AsyncGenerator[Image, None]:
    """Iteratively image, segment and wash each slide until it is sufficiently destained.

    For every loaded slide the robot carries it to the microscope, an image is
    acquired and segmented, and the stain percentage is measured. While the
    sample is still over-stained the slide is taken to the Opentrons for a
    washing step and re-imaged, up to ``max_iterations`` times.
    """

    for slide in loaded_slides:
        # Pick from tray and carry to the microscope.
        await robot.pickup_slide_from_pickupstation()
        await robot.move_slide_to_microscope()
        await microscope.move_to_position("imaging_position")

        image = await microscope.acquire_image()
        yield image
        segmented = await segmenter.segment_image(image)
        yield segmented
        stain = await analyzer.calculate_stain_percentage(segmented)

        iteration = 0
        while stain > 0.8 and iteration < max_iterations:
            # Carry to Opentrons and run the washing/staining protocol.
            await robot.pickup_slide_from_microscope()
            await robot.move_slide_to_opentron()
            await _run_protocol(opentrons, slide.protocol)

            # Bring back to microscope and re-image.
            await robot.pickup_slide_from_opentron()
            await robot.move_slide_to_microscope()

            image = await microscope.acquire_image()
            yield image
            segmented = await segmenter.segment_image(image)
            yield segmented
            stain = await analyzer.calculate_stain_percentage(segmented)

            iteration += 1
            log(f"Iteration {iteration}, Stain Percentage: {stain:.2%}")

        if iteration == max_iterations:
            log("Reached maximum iterations without sufficient staining.")

        # Return the slide to the tray.
        await robot.pickup_slide_from_microscope()
        await robot.move_slide_to_pickupstation()


@register
async def run_concurrent_staining(
    robot: FarinoLike,
    opentrons: OT2Like,
    microscope: FrameLike,
    stitcher: StitcherLike,
    segmenter: SegmenterLike,
    analyzer: AnalyzerLike,
    state: AppState,
    loaded_slides: list[Slide],
    tile_positions: Annotated[
        list[str],
        withDescription("The named stage positions to visit and image per slide."),
    ],
    target_stain_percentage: float = 0.8,
    max_rounds: int = 5,
) -> AsyncGenerator[Image, None]:
    """Concurrent staining workflow with an internal task-tracking scheduler.

    The robot and single microscope are a serial bottleneck, so only one slide is
    ever physically handled at a time. The expensive compute — stitching the tile
    grid, Cellpose segmentation, stain quantification — is independent per slide
    and is fired off as a background ``asyncio`` task the moment a slide's tiles
    are acquired. While those tasks run on the agent fleet, the robot keeps moving
    the next slide.

    The loop below keeps track of the in-flight compute tasks. As each analysis
    finishes we check whether the slide is *under*-stained (too few stained cells,
    ``percentage < target_stain_percentage``). If so the slide is queued for a
    staining run on the Opentrons and then re-imaged, up to ``max_rounds`` times.

    Every transition is mirrored into the published ``AppState`` so observers can
    follow each slide moving through queued -> imaging -> analyzing -> staining ->
    done, along with its staining-round count and latest stitched/segmented images.
    """

    rounds: dict[str, int] = {slide.name: 0 for slide in loaded_slides}
    for slide in loaded_slides:
        state.slide_status[slide.name] = SlideStatus.QUEUED
        state.staining_rounds[slide.name] = 0

    # Serial physical work queue: ("image", slide) or ("stain", slide).
    physical: deque[tuple[str, Slide]] = deque(
        ("image", slide) for slide in loaded_slides
    )
    # In-flight stitch -> segment -> analyze tasks, keyed to their slide.
    compute: dict[asyncio.Task[tuple[Image, Image, float]], Slide] = {}

    async def analyze(tiles: list[Image]) -> tuple[Image, Image, float]:
        """Offloaded compute: stitch the tiles, segment with Cellpose, measure stain."""
        stitched = await stitcher.stitch_images(tiles)
        segmented = await segmenter.segment_image(stitched)
        percentage = await analyzer.calculate_stain_percentage(segmented)
        return stitched, segmented, percentage

    async def image_slide(slide: Slide) -> None:
        """Serial physical op: fetch slide, scan tiles, return it, spawn compute."""
        state.currently_imaging_slide = slide.name
        state.slide_status[slide.name] = SlideStatus.IMAGING
        await robot.pickup_slide_from_pickupstation()
        await robot.move_slide_to_microscope()
        tiles = await _scan_tiles(microscope, tile_positions)
        await robot.pickup_slide_from_microscope()
        await robot.move_slide_to_pickupstation()
        state.currently_imaging_slide = None
        state.slide_status[slide.name] = SlideStatus.ANALYZING
        compute[asyncio.ensure_future(analyze(tiles))] = slide

    async def stain_slide(slide: Slide) -> None:
        """Serial physical op: carry the slide to the Opentrons and stain it."""
        state.slide_status[slide.name] = SlideStatus.STAINING
        await robot.pickup_slide_from_pickupstation()
        await robot.move_slide_to_opentron()
        await _run_protocol(opentrons, slide.protocol)
        await robot.pickup_slide_from_opentron()
        await robot.move_slide_to_pickupstation()

    while physical or compute:
        # 1. Harvest any compute that has finished and decide on more staining.
        for task in [t for t in compute if t.done()]:
            slide = compute.pop(task)
            stitched, segmented, percentage = task.result()
            state.latest_images[slide.name] = stitched
            state.latest_segmented[slide.name] = segmented
            yield stitched
            yield segmented

            if percentage < target_stain_percentage and rounds[slide.name] < max_rounds:
                rounds[slide.name] += 1
                state.staining_rounds[slide.name] = rounds[slide.name]
                log(
                    f"Slide {slide.name}: {percentage:.2%} stained — staining "
                    f"(round {rounds[slide.name]})."
                )
                physical.append(("stain", slide))
            else:
                state.slide_status[slide.name] = SlideStatus.DONE
                log(f"Slide {slide.name}: {percentage:.2%} stained — done.")

        # 2. Run a single physical operation if one is queued; the hardware is
        #    serial so we only ever do one at a time, keeping the compute fleet
        #    busy in the background.
        if physical:
            op, slide = physical.popleft()
            if op == "image":
                await image_slide(slide)
            else:
                await stain_slide(slide)
                physical.append(("image", slide))  # re-image after staining
        elif compute:
            # Nothing physical to do right now — wait for the next analysis.
            await asyncio.wait(set(compute), return_when=asyncio.FIRST_COMPLETED)


if __name__ == "__main__":
    load_dotenv()  # Load environment variables from .env file
    redeem_token = os.getenv("REDEEM_TOKEN", None)
    with easy(identifier="stainstorm", redeem_token=redeem_token) as app:
        app.run()
