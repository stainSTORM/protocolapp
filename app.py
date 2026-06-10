import asyncio
from collections import deque
from typing import Annotated, AsyncGenerator, Dict, Optional, Protocol
from dataclasses import field

from mikro_next.api.schema import Image
from arkitekt_next import easy, register, state, startup, log
from rekuest_next.declare import declare, declare_state
from rekuest_next.structures.model import model
from rekuest_next.widgets import withDescription, withStateChoices


# The StainStorm meta-app no longer ships its own @protocol stubs. Instead it
# *declares* the remote apps it depends on (robot, opentrons, microscope,
# stitcher, segmenter, analyzer) as typing.Protocol classes. arkitekt-next
# injects a live proxy for each declared dependency as a typed parameter of the
# registered function, so the orchestration below simply awaits methods on those
# proxies. All declared methods are async, so independent remote calls can be
# fanned out concurrently with asyncio.gather / asyncio.as_completed.


# --- Declared remote state shapes ------------------------------------------
# @declare_state describes the observable state an app publishes. We reference
# fields of these states from input widgets via withStateChoices(...).


@declare_state
class TrajectoriesState:
    available_trajectories: Optional[list[str]] = None


@declare_state
class RunState:
    available_protocols: Optional[list[str]] = None


# --- Declared remote apps ---------------------------------------------------


@declare(app="arkirino")
class ArkirinoLike(Protocol):
    """The robot arm that moves slides between the tray, microscope and opentrons."""

    trajectories: TrajectoriesState

    async def run_trajectory(
        self, name: str, speed: Optional[int] = None, acceleration: Optional[int] = None
    ) -> None:
        """Execute a saved named trajectory on the robot."""
        ...

    async def grip(self) -> None:
        """Close the gripper to hold a slide."""
        ...

    async def ungrip(self) -> None:
        """Open the gripper to release a slide."""
        ...


@declare(app="OT2")
class OT2Like(Protocol):
    """The Opentrons OT-2 liquid handler that runs washing protocols."""

    run: RunState

    async def run_protocol(self, protocol: str) -> None:
        """Run a named protocol on the Opentrons (e.g. a washing step)."""
        ...


@declare(app="openuc", min=1, max=1)
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


# TODO: set app=... to the real analyzer app identifier once it is available.
@declare(app="analyzer")
class AnalyzerLike(Protocol):
    """An analysis app that quantifies staining from a segmentation mask."""

    async def calculate_stain_percentage(self, image: Image) -> float:
        """Calculate the percentage of stained cells from a label mask."""
        ...


# --- Structured input model -------------------------------------------------
# The withStateChoices paths reference the @register parameter names below
# (`opentrons` and `robot`) followed by the declared-state attribute and field.


@model
class Slide:
    name: Annotated[str, withDescription("Display name of the slide.")]
    protocol: Annotated[
        str,
        withStateChoices("opentrons.run.available_protocols"),
        withDescription("The Opentrons washing protocol to run for this slide."),
    ]
    trajectory: Annotated[
        str,
        withStateChoices("robot.trajectories.available_trajectories"),
        withDescription("The Arkirino trajectory to reach this slide in the tray."),
    ]


# --- Local app state --------------------------------------------------------


class SlideStatus:
    """The stages a slide moves through during the concurrent staining workflow."""

    QUEUED = "queued"  # waiting to be imaged
    IMAGING = "imaging"  # on the microscope, acquiring tiles
    ANALYZING = "analyzing"  # stitch -> segment -> quantify running in the background
    STAINING = "staining"  # on the Opentrons being stained
    DONE = "done"  # reached target stain (or exhausted its staining rounds)


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


async def _carry_slide(
    robot: ArkirinoLike, from_trajectory: str, to_trajectory: str
) -> None:
    """Pick the slide up at ``from_trajectory`` and release it at ``to_trajectory``."""
    await robot.run_trajectory(from_trajectory)
    await robot.grip()
    await robot.run_trajectory(to_trajectory)
    await robot.ungrip()


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
    robot: ArkirinoLike,
    opentrons: OT2Like,
    microscope: FrameLike,
    segmenter: SegmenterLike,
    analyzer: AnalyzerLike,
    loaded_slides: list[Slide],
    microscope_trajectory: Annotated[
        str,
        withStateChoices("robot.trajectories.available_trajectories"),
        withDescription("The Arkirino trajectory to reach the microscope."),
    ],
    opentrons_trajectory: Annotated[
        str,
        withStateChoices("robot.trajectories.available_trajectories"),
        withDescription("The Arkirino trajectory to reach the Opentrons."),
    ],
    max_iterations: int = 5,
) -> AsyncGenerator[Image, None]:
    """Iteratively image, segment and wash each slide until it is sufficiently destained.

    For every loaded slide the robot carries it to the microscope, an image is
    acquired and segmented, and the stain percentage is measured. While the
    sample is still over-stained the slide is taken to the Opentrons for a
    washing step and re-imaged, up to ``max_iterations`` times.
    """

    for slide in loaded_slides:
        # Fetch the slide from the tray and carry it to the microscope.
        await _carry_slide(robot, slide.trajectory, microscope_trajectory)
        await microscope.move_to_position("imaging_position")

        # Initial acquisition and segmentation.
        image = await microscope.acquire_image()
        yield image
        segmented = await segmenter.segment_image(image)
        yield segmented
        stain = await analyzer.calculate_stain_percentage(segmented)

        iteration = 0
        while stain > 0.8 and iteration < max_iterations:
            # Carry the slide to the Opentrons and run the washing protocol.
            await _carry_slide(robot, microscope_trajectory, opentrons_trajectory)
            await opentrons.run_protocol(slide.protocol)

            # Bring it back to the microscope and re-image.
            await _carry_slide(robot, opentrons_trajectory, microscope_trajectory)

            image = await microscope.acquire_image()
            yield image
            segmented = await segmenter.segment_image(image)
            yield segmented
            stain = await analyzer.calculate_stain_percentage(segmented)

            iteration += 1
            log(f"Iteration {iteration}, Stain Percentage: {stain:.2%}")

        if iteration == max_iterations:
            log("Reached maximum iterations without sufficient staining.")

        # Return the slide to its place in the tray.
        await _carry_slide(robot, microscope_trajectory, slide.trajectory)


@register
async def run_concurrent_staining(
    robot: ArkirinoLike,
    opentrons: OT2Like,
    microscope: FrameLike,
    stitcher: StitcherLike,
    segmenter: SegmenterLike,
    analyzer: AnalyzerLike,
    state: AppState,
    loaded_slides: list[Slide],
    microscope_trajectory: Annotated[
        str,
        withStateChoices("robot.trajectories.available_trajectories"),
        withDescription("The Arkirino trajectory to reach the microscope."),
    ],
    opentrons_trajectory: Annotated[
        str,
        withStateChoices("robot.trajectories.available_trajectories"),
        withDescription("The Arkirino trajectory to reach the Opentrons."),
    ],
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
        """Serial physical op: scan the slide's tiles, return it, spawn compute."""
        state.currently_imaging_slide = slide.name
        state.slide_status[slide.name] = SlideStatus.IMAGING
        await _carry_slide(robot, slide.trajectory, microscope_trajectory)
        tiles = await _scan_tiles(microscope, tile_positions)
        await _carry_slide(robot, microscope_trajectory, slide.trajectory)
        state.currently_imaging_slide = None
        state.slide_status[slide.name] = SlideStatus.ANALYZING
        compute[asyncio.ensure_future(analyze(tiles))] = slide

    async def stain_slide(slide: Slide) -> None:
        """Serial physical op: carry the slide to the Opentrons and stain it."""
        state.slide_status[slide.name] = SlideStatus.STAINING
        await _carry_slide(robot, slide.trajectory, opentrons_trajectory)
        await opentrons.run_protocol(slide.protocol)
        await _carry_slide(robot, opentrons_trajectory, slide.trajectory)

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
    with easy(identifier="stainstorm") as app:
        app.run()
