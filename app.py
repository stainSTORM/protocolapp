from typing import Annotated, Dict, Generator, Optional, Protocol
from dataclasses import field

from mikro_next.api.schema import Image
from arkitekt_next import easy, register, state, startup, log
from rekuest_next.declare import declare, declare_state
from rekuest_next.structures.model import model
from rekuest_next.widgets import withDescription, withStateChoices


# The StainStorm meta-app no longer ships its own @protocol stubs. Instead it
# *declares* the remote apps it depends on (robot, opentrons, microscope,
# segmenter, analyzer) as typing.Protocol classes. arkitekt-next injects a live
# proxy for each declared dependency as a typed parameter of the registered
# function, so the orchestration below simply calls methods on those proxies.


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

    def run_trajectory(
        self, name: str, speed: Optional[int] = None, acceleration: Optional[int] = None
    ) -> None:
        """Execute a saved named trajectory on the robot."""
        ...

    def grip(self) -> None:
        """Close the gripper to hold a slide."""
        ...

    def ungrip(self) -> None:
        """Open the gripper to release a slide."""
        ...


@declare(app="OT2")
class OT2Like(Protocol):
    """The Opentrons OT-2 liquid handler that runs washing protocols."""

    run: RunState

    def run_protocol(self, protocol: str) -> None:
        """Run a named protocol on the Opentrons (e.g. a washing step)."""
        ...


@declare(app="openuc", min=1, max=1)
class FrameLike(Protocol):
    """The microscope that acquires images of a sample."""

    def acquire_image(self) -> Image:
        """Acquire an image from the microscope sensor."""
        ...

    def move_to_position(self, position: str) -> None:
        """Move the stage to a named position."""
        ...


@declare(app="starmist", min=2, max=10)
class SegmenterLike(Protocol):
    """A segmentation app that labels cells in an image."""

    def segment_image(self, image: Image) -> Image:
        """Segment an image, returning a label mask of stained/unstained cells."""
        ...


# TODO: set app=... to the real analyzer app identifier once it is available.
@declare(app="analyzer")
class AnalyzerLike(Protocol):
    """An analysis app that quantifies staining from a segmentation mask."""

    def calculate_stain_percentage(self, image: Image) -> float:
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


@state
class AppState:
    currently_imaging_slide: Annotated[
        Optional[str],
        withDescription("The name of the slide currently being imaged."),
    ] = None
    latest_images: Annotated[
        Dict[str, Image],
        withDescription("The latest acquired image per slide name."),
    ] = field(default_factory=dict)
    latest_segmented: Annotated[
        Dict[str, Image],
        withDescription("The latest segmentation mask per slide name."),
    ] = field(default_factory=dict)


@startup
def startup_hook() -> AppState:
    """Initialize the app state when the agent boots."""
    return AppState()


# --- The registered protocol ------------------------------------------------


@register
def run_stainstorm(
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
) -> Generator[Image, None, None]:
    """Iteratively image, segment and wash each slide until it is sufficiently destained.

    For every loaded slide the robot carries it to the microscope, an image is
    acquired and segmented, and the stain percentage is measured. While the
    sample is still over-stained the slide is taken to the Opentrons for a
    washing step and re-imaged, up to ``max_iterations`` times.
    """

    for slide in loaded_slides:
        # Fetch the slide from the tray and carry it to the microscope.
        robot.run_trajectory(slide.trajectory)
        robot.grip()
        robot.run_trajectory(microscope_trajectory)
        robot.ungrip()
        microscope.move_to_position("imaging_position")

        # Initial acquisition and segmentation.
        image = microscope.acquire_image()
        yield image
        segmented = segmenter.segment_image(image)
        yield segmented
        stain = analyzer.calculate_stain_percentage(segmented)

        iteration = 0
        while stain > 0.8 and iteration < max_iterations:
            # Carry the slide to the Opentrons and run the washing protocol.
            robot.grip()
            robot.run_trajectory(opentrons_trajectory)
            robot.ungrip()
            opentrons.run_protocol(slide.protocol)

            # Bring it back to the microscope and re-image.
            robot.grip()
            robot.run_trajectory(microscope_trajectory)
            robot.ungrip()

            image = microscope.acquire_image()
            yield image
            segmented = segmenter.segment_image(image)
            yield segmented
            stain = analyzer.calculate_stain_percentage(segmented)

            iteration += 1
            log(f"Iteration {iteration}, Stain Percentage: {stain:.2%}")

        if iteration == max_iterations:
            log("Reached maximum iterations without sufficient staining.")

        # Return the slide to its place in the tray.
        robot.grip()
        robot.run_trajectory(slide.trajectory)
        robot.ungrip()


if __name__ == "__main__":
    with easy(identifier="stainstorm") as app:
        app.run()
