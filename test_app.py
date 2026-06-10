"""Unit tests for the StainStorm ``run_stainstorm`` protocol.

``run_stainstorm`` is a ``@register``-decorated generator that orchestrates a
set of *declared* remote dependencies (robot, opentrons, microscope, segmenter,
analyzer). ``register`` returns a ``WrappedFunction`` whose ``__call__`` simply
invokes the underlying function, so we can call it directly and inject plain
local fakes that satisfy each declared ``Protocol`` structurally.

The fakes record every call so we can assert on the orchestration logic — the
movement sequence, the washing retry loop, the threshold/max-iteration cutoffs
and the images that flow through segmentation and analysis.
"""

from typing import Optional, cast

import pytest

from mikro_next.api.schema import Image

import app
from app import RunState, Slide, TrajectoriesState, run_stainstorm


def _img(tag: str) -> Image:
    """A lightweight stand-in for a real mikro Image (only identity matters here)."""
    return cast(Image, tag)


# --- Local fake implementations of the declared dependencies ----------------


class FakeRobot:
    """Stand-in for ``ArkirinoLike``. Records the ordered call log."""

    def __init__(self) -> None:
        self.trajectories = TrajectoriesState()
        self.trajectories.available_trajectories = ["traj-1", "traj-2"]
        self.calls: list[tuple] = []

    def run_trajectory(
        self,
        name: str,
        speed: Optional[int] = None,
        acceleration: Optional[int] = None,
    ) -> None:
        self.calls.append(("run_trajectory", name, speed, acceleration))

    def grip(self) -> None:
        self.calls.append(("grip",))

    def ungrip(self) -> None:
        self.calls.append(("ungrip",))


class FakeOpentrons:
    """Stand-in for ``OT2Like``. Records the protocols it was asked to run."""

    def __init__(self) -> None:
        self.run = RunState()
        self.run.available_protocols = ["wash-A", "wash-B"]
        self.run_protocols: list[str] = []

    def run_protocol(self, protocol: str) -> None:
        self.run_protocols.append(protocol)


class FakeMicroscope:
    """Stand-in for ``FrameLike``. Hands out a fresh sentinel image per acquire."""

    def __init__(self) -> None:
        self.positions: list[str] = []
        self.acquired: list[Image] = []
        self._counter = 0

    def acquire_image(self) -> Image:
        self._counter += 1
        image = _img(f"image-{self._counter}")
        self.acquired.append(image)
        return image

    def move_to_position(self, position: str) -> None:
        self.positions.append(position)


class FakeSegmenter:
    """Stand-in for ``SegmenterLike``. Returns a sentinel mask per input image."""

    def __init__(self) -> None:
        self.inputs: list[Image] = []

    def segment_image(self, image: Image) -> Image:
        self.inputs.append(image)
        return _img(f"segmented-{image}")


class FakeAnalyzer:
    """Stand-in for ``AnalyzerLike``. Returns a scripted sequence of stain %s."""

    def __init__(self, stains: list[float]) -> None:
        self._stains = list(stains)
        self.inputs: list[Image] = []

    def calculate_stain_percentage(self, image: Image) -> float:
        self.inputs.append(image)
        assert self._stains, "FakeAnalyzer ran out of scripted stain values"
        return self._stains.pop(0)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def robot() -> FakeRobot:
    return FakeRobot()


@pytest.fixture
def opentrons() -> FakeOpentrons:
    return FakeOpentrons()


@pytest.fixture
def microscope() -> FakeMicroscope:
    return FakeMicroscope()


@pytest.fixture
def segmenter() -> FakeSegmenter:
    return FakeSegmenter()


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture every message passed to ``app.log``."""
    messages: list[str] = []
    monkeypatch.setattr(app, "log", lambda message: messages.append(message))
    return messages


def drive(
    *,
    robot: FakeRobot,
    opentrons: FakeOpentrons,
    microscope: FakeMicroscope,
    segmenter: FakeSegmenter,
    analyzer: FakeAnalyzer,
    loaded_slides: list[Slide],
    microscope_trajectory: str = "to_microscope",
    opentrons_trajectory: str = "to_opentrons",
    max_iterations: int = 5,
) -> list[Image]:
    """Run the generator to completion and return everything it yielded."""
    return list(
        run_stainstorm(
            robot=robot,
            opentrons=opentrons,
            microscope=microscope,
            segmenter=segmenter,
            analyzer=analyzer,
            loaded_slides=loaded_slides,
            microscope_trajectory=microscope_trajectory,
            opentrons_trajectory=opentrons_trajectory,
            max_iterations=max_iterations,
        )
    )


# --- Tests ------------------------------------------------------------------


def test_no_washing_when_below_threshold(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """A slide already below the 0.8 threshold is imaged once and never washed."""
    analyzer = FakeAnalyzer([0.5])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    yielded = drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

    # One acquisition + its segmentation are yielded; no washing iterations.
    assert yielded == [_img("image-1"), _img("segmented-image-1")]
    assert opentrons.run_protocols == []
    assert microscope.acquired == [_img("image-1")]
    assert analyzer.inputs == [_img("segmented-image-1")]
    assert captured_logs == []


def test_full_robot_sequence_for_single_unwashed_slide(
    robot, opentrons, microscope, segmenter
):
    """The exact pick-up / carry / image / return movement sequence is correct."""
    analyzer = FakeAnalyzer([0.1])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-slide")

    drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
        microscope_trajectory="traj-scope",
    )

    assert robot.calls == [
        ("run_trajectory", "traj-slide", None, None),  # go to slide in tray
        ("grip",),  # pick it up
        ("run_trajectory", "traj-scope", None, None),  # carry to microscope
        ("ungrip",),  # release onto stage
        ("grip",),  # pick back up
        ("run_trajectory", "traj-slide", None, None),  # return to tray
        ("ungrip",),  # drop into tray
    ]
    assert microscope.positions == ["imaging_position"]


def test_washes_until_stain_drops_below_threshold(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """Over-stained slides are re-washed until the stain falls under 0.8."""
    # initial 0.9 -> wash -> 0.9 -> wash -> 0.5 (stops)
    analyzer = FakeAnalyzer([0.9, 0.9, 0.5])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    yielded = drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

    # Two washing iterations, each running the slide's protocol.
    assert opentrons.run_protocols == ["wash-A", "wash-A"]
    # 1 initial + 2 re-acquisitions => 3 images, each followed by its mask.
    assert microscope.acquired == [_img("image-1"), _img("image-2"), _img("image-3")]
    assert yielded == [
        _img("image-1"),
        _img("segmented-image-1"),
        _img("image-2"),
        _img("segmented-image-2"),
        _img("image-3"),
        _img("segmented-image-3"),
    ]
    # Per-iteration progress logs, but not the max-iterations warning.
    assert len(captured_logs) == 2
    assert all("Stain Percentage" in m for m in captured_logs)
    assert not any("maximum iterations" in m for m in captured_logs)


def test_stops_at_max_iterations(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """A stubbornly stained slide stops after ``max_iterations`` washes."""
    analyzer = FakeAnalyzer([0.95] * 10)  # always above threshold
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
        max_iterations=3,
    )

    assert opentrons.run_protocols == ["wash-A"] * 3
    # 1 initial + 3 washes => 4 stain measurements.
    assert len(analyzer.inputs) == 4
    assert any("maximum iterations" in m for m in captured_logs)


def test_segmenter_and_analyzer_receive_chained_inputs(
    robot, opentrons, microscope, segmenter
):
    """The segmenter sees acquired images; the analyzer sees their masks."""
    analyzer = FakeAnalyzer([0.5])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

    assert segmenter.inputs == [_img("image-1")]
    assert analyzer.inputs == [_img("segmented-image-1")]


def test_multiple_slides_each_visited_and_returned(
    robot, opentrons, microscope, segmenter
):
    """Every loaded slide is independently imaged using its own trajectory."""
    analyzer = FakeAnalyzer([0.2, 0.2])  # both below threshold
    slides = [
        Slide(name="s1", protocol="wash-A", trajectory="traj-1"),
        Slide(name="s2", protocol="wash-B", trajectory="traj-2"),
    ]

    yielded = drive(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=slides,
    )

    assert microscope.acquired == [_img("image-1"), _img("image-2")]
    assert len(yielded) == 4  # 2 slides * (image + mask)
    assert opentrons.run_protocols == []
    # Each slide's own trajectory is used to fetch and return it.
    fetched = [c[1] for c in robot.calls if c[0] == "run_trajectory"]
    assert "traj-1" in fetched and "traj-2" in fetched


def test_lazy_generator_does_not_run_until_iterated(
    robot, opentrons, microscope, segmenter
):
    """Constructing the generator performs no work; iteration drives it."""
    analyzer = FakeAnalyzer([0.5])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    gen = run_stainstorm(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
        microscope_trajectory="to_microscope",
        opentrons_trajectory="to_opentrons",
    )

    assert robot.calls == []  # nothing happened yet
    next(gen)  # pull the first yield
    assert robot.calls  # now the robot has started moving
