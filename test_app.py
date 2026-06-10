"""Unit tests for the StainStorm registered protocols.

The registered functions (``run_stainstorm``, ``stitch_and_segment``,
``stitch_and_segment_optimized``) are ``@register``-decorated **async**
generators that orchestrate a set of *declared* remote dependencies. ``register``
returns a ``WrappedFunction`` whose ``__call__`` invokes the underlying function,
so we can call it directly and inject plain local async fakes that satisfy each
declared ``Protocol`` structurally.

Every declared method is ``async def``; the fakes mirror that. Tests drive the
async generators with ``asyncio.run`` and assert on the orchestration logic — the
movement sequence, the washing retry loop, the stitch->segment pipeline, and that
the *optimized* variant runs the per-slide compute concurrently while keeping the
physical acquisition serial.
"""

import asyncio
from typing import Optional, cast

import pytest

from mikro_next.api.schema import Image

import app
from app import (
    AppState,
    RunState,
    Slide,
    SlideStatus,
    TrajectoriesState,
    run_concurrent_staining,
    run_stainstorm,
)


def _img(tag: str) -> Image:
    """A lightweight stand-in for a real mikro Image (only identity matters here)."""
    return cast(Image, tag)


def collect(agen) -> list[Image]:
    """Drive an async generator to completion and return everything it yielded."""

    async def _consume() -> list[Image]:
        return [item async for item in agen]

    return asyncio.run(_consume())


# --- Local async fake implementations of the declared dependencies ----------


class FakeRobot:
    """Stand-in for ``ArkirinoLike``. Records the ordered call log."""

    def __init__(self) -> None:
        self.trajectories = TrajectoriesState()
        self.trajectories.available_trajectories = ["traj-1", "traj-2"]
        self.calls: list[tuple] = []

    async def run_trajectory(
        self,
        name: str,
        speed: Optional[int] = None,
        acceleration: Optional[int] = None,
    ) -> None:
        self.calls.append(("run_trajectory", name, speed, acceleration))

    async def grip(self) -> None:
        self.calls.append(("grip",))

    async def ungrip(self) -> None:
        self.calls.append(("ungrip",))


class FakeOpentrons:
    """Stand-in for ``OT2Like``. Records the protocols it was asked to run."""

    def __init__(self) -> None:
        self.run = RunState()
        self.run.available_protocols = ["wash-A", "wash-B"]
        self.run_protocols: list[str] = []

    async def run_protocol(self, protocol: str) -> None:
        self.run_protocols.append(protocol)


class FakeMicroscope:
    """Stand-in for ``FrameLike``. Hands out a fresh sentinel image per acquire."""

    def __init__(self, timeline: Optional[list] = None) -> None:
        self.timeline = timeline if timeline is not None else []
        self.positions: list[str] = []
        self.acquired: list[Image] = []
        self._counter = 0

    async def acquire_image(self) -> Image:
        self._counter += 1
        image = _img(f"image-{self._counter}")
        self.acquired.append(image)
        self.timeline.append(("acquire", image))
        return image

    async def move_to_position(self, position: str) -> None:
        self.positions.append(position)


class FakeStitcher:
    """Stand-in for ``StitcherLike``. Returns a sentinel composite per call."""

    def __init__(self, timeline: Optional[list] = None) -> None:
        self.timeline = timeline if timeline is not None else []
        self.inputs: list[list[Image]] = []

    async def stitch_images(self, images: list[Image]) -> Image:
        self.inputs.append(list(images))
        stitched = _img(f"stitched-{len(self.inputs)}")
        self.timeline.append(("stitch", stitched))
        return stitched


class FakeSegmenter:
    """Stand-in for ``SegmenterLike`` (Cellpose). Returns a sentinel mask per image.

    An optional ``barrier`` lets a test prove concurrent execution: every call
    waits on the barrier, so the generator only completes if enough calls are
    in flight simultaneously.
    """

    def __init__(
        self,
        timeline: Optional[list] = None,
        barrier: Optional[asyncio.Barrier] = None,
    ) -> None:
        self.timeline = timeline if timeline is not None else []
        self.barrier = barrier
        self.inputs: list[Image] = []

    async def segment_image(self, image: Image) -> Image:
        if self.barrier is not None:
            await self.barrier.wait()
        self.inputs.append(image)
        segmented = _img(f"segmented-{image}")
        self.timeline.append(("segment", segmented))
        return segmented


class FakeAnalyzer:
    """Stand-in for ``AnalyzerLike``. Returns a scripted sequence of stain %s."""

    def __init__(self, stains: list[float]) -> None:
        self._stains = list(stains)
        self.inputs: list[Image] = []

    async def calculate_stain_percentage(self, image: Image) -> float:
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
def stitcher() -> FakeStitcher:
    return FakeStitcher()


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture every message passed to ``app.log``."""
    messages: list[str] = []
    monkeypatch.setattr(app, "log", lambda message: messages.append(message))
    return messages


def drive_stainstorm(
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
    return collect(
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


# --- run_stainstorm tests ---------------------------------------------------


def test_no_washing_when_below_threshold(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """A slide already below the 0.8 threshold is imaged once and never washed."""
    analyzer = FakeAnalyzer([0.5])
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    yielded = drive_stainstorm(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

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

    drive_stainstorm(
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
        ("run_trajectory", "traj-scope", None, None),  # go back to fetch it
        ("grip",),  # pick it back up
        ("run_trajectory", "traj-slide", None, None),  # carry back to tray
        ("ungrip",),  # drop into tray
    ]
    assert microscope.positions == ["imaging_position"]


def test_washes_until_stain_drops_below_threshold(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """Over-stained slides are re-washed until the stain falls under 0.8."""
    analyzer = FakeAnalyzer([0.9, 0.9, 0.5])  # initial -> wash -> wash -> stop
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    yielded = drive_stainstorm(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

    assert opentrons.run_protocols == ["wash-A", "wash-A"]
    assert microscope.acquired == [_img("image-1"), _img("image-2"), _img("image-3")]
    assert yielded == [
        _img("image-1"),
        _img("segmented-image-1"),
        _img("image-2"),
        _img("segmented-image-2"),
        _img("image-3"),
        _img("segmented-image-3"),
    ]
    assert len(captured_logs) == 2
    assert all("Stain Percentage" in m for m in captured_logs)
    assert not any("maximum iterations" in m for m in captured_logs)


def test_stops_at_max_iterations(
    robot, opentrons, microscope, segmenter, captured_logs
):
    """A stubbornly stained slide stops after ``max_iterations`` washes."""
    analyzer = FakeAnalyzer([0.95] * 10)  # always above threshold
    slide = Slide(name="s1", protocol="wash-A", trajectory="traj-1")

    drive_stainstorm(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
        max_iterations=3,
    )

    assert opentrons.run_protocols == ["wash-A"] * 3
    assert len(analyzer.inputs) == 4  # 1 initial + 3 washes
    assert any("maximum iterations" in m for m in captured_logs)


def test_multiple_slides_each_visited_and_returned(
    robot, opentrons, microscope, segmenter
):
    """Every loaded slide is independently imaged using its own trajectory."""
    analyzer = FakeAnalyzer([0.2, 0.2])  # both below threshold
    slides = [
        Slide(name="s1", protocol="wash-A", trajectory="traj-1"),
        Slide(name="s2", protocol="wash-B", trajectory="traj-2"),
    ]

    yielded = drive_stainstorm(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=slides,
    )

    assert microscope.acquired == [_img("image-1"), _img("image-2")]
    assert len(yielded) == 4
    assert opentrons.run_protocols == []
    fetched = [c[1] for c in robot.calls if c[0] == "run_trajectory"]
    assert "traj-1" in fetched and "traj-2" in fetched


# --- run_concurrent_staining tests ------------------------------------------


def drive_concurrent_staining(
    *,
    robot: FakeRobot,
    opentrons: FakeOpentrons,
    microscope: FakeMicroscope,
    stitcher: FakeStitcher,
    segmenter: FakeSegmenter,
    analyzer: FakeAnalyzer,
    loaded_slides: list[Slide],
    state: Optional[AppState] = None,
    microscope_trajectory: str = "to_microscope",
    opentrons_trajectory: str = "to_opentrons",
    tile_positions: Optional[list[str]] = None,
    target_stain_percentage: float = 0.8,
    max_rounds: int = 5,
) -> list[Image]:
    return collect(
        run_concurrent_staining(
            robot=robot,
            opentrons=opentrons,
            microscope=microscope,
            stitcher=stitcher,
            segmenter=segmenter,
            analyzer=analyzer,
            state=state if state is not None else AppState(),
            loaded_slides=loaded_slides,
            microscope_trajectory=microscope_trajectory,
            opentrons_trajectory=opentrons_trajectory,
            tile_positions=tile_positions or ["p1", "p2"],
            target_stain_percentage=target_stain_percentage,
            max_rounds=max_rounds,
        )
    )


def test_compute_is_offloaded_and_runs_concurrently():
    """Compute for all slides is fired off as tasks and runs at the same time.

    Each segmentation blocks on a barrier sized to the slide count. The scheduler
    images every slide first (spawning a compute task each) before awaiting, so
    all segmentations reach the barrier together. A sequential implementation that
    awaited each analysis inline would only ever have one in flight — the barrier
    would never release and this would time out.
    """
    n = 3
    slides = [
        Slide(name=f"s{i}", protocol="stain-A", trajectory=f"traj-{i}")
        for i in range(n)
    ]

    async def _run() -> list[Image]:
        barrier = asyncio.Barrier(n)
        agen = run_concurrent_staining(
            robot=FakeRobot(),
            opentrons=FakeOpentrons(),
            microscope=FakeMicroscope(),
            stitcher=FakeStitcher(),
            segmenter=FakeSegmenter(barrier=barrier),
            analyzer=FakeAnalyzer([0.95] * n),  # all above target -> no staining
            state=AppState(),
            loaded_slides=slides,
            microscope_trajectory="to_microscope",
            opentrons_trajectory="to_opentrons",
            tile_positions=["p1", "p2"],
            target_stain_percentage=0.8,
        )
        return [item async for item in agen]

    yielded = asyncio.run(asyncio.wait_for(_run(), timeout=3.0))

    assert len(yielded) == 2 * n  # stitched + segmented per slide


def test_understained_slide_is_stained_then_reimaged(
    robot, opentrons, microscope, stitcher, segmenter, captured_logs
):
    """A slide below target is routed to the Opentrons, stained, then re-imaged."""
    # First analysis under target -> stain; after staining it clears the target.
    analyzer = FakeAnalyzer([0.1, 0.9])
    slide = Slide(name="s1", protocol="stain-A", trajectory="traj-1")

    yielded = drive_concurrent_staining(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        stitcher=stitcher,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
    )

    # Exactly one staining run, then a second imaging pass.
    assert opentrons.run_protocols == ["stain-A"]
    assert len(stitcher.inputs) == 2  # imaged twice
    assert len(yielded) == 4  # (stitched + segmented) per imaging
    # The robot visited the opentrons trajectory to stain.
    visited = [c[1] for c in robot.calls if c[0] == "run_trajectory"]
    assert "to_opentrons" in visited
    # The under-stained round and the final completion are both logged.
    assert any("staining" in m for m in captured_logs)
    assert any("done" in m for m in captured_logs)


def test_stops_staining_at_max_rounds(
    robot, opentrons, microscope, stitcher, segmenter, captured_logs
):
    """A slide that never reaches target stops after ``max_rounds`` staining runs."""
    analyzer = FakeAnalyzer([0.1] * 10)  # always under target
    slide = Slide(name="s1", protocol="stain-A", trajectory="traj-1")

    drive_concurrent_staining(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        stitcher=stitcher,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=[slide],
        max_rounds=2,
    )

    assert opentrons.run_protocols == ["stain-A", "stain-A"]
    # 1 initial imaging + 2 re-images after staining.
    assert len(stitcher.inputs) == 3
    assert any("done" in m for m in captured_logs)


def test_well_stained_slides_are_not_stained(
    robot, opentrons, microscope, stitcher, segmenter, captured_logs
):
    """Slides already at/above target are imaged once and never touched again."""
    slides = [
        Slide(name="s1", protocol="stain-A", trajectory="traj-1"),
        Slide(name="s2", protocol="stain-B", trajectory="traj-2"),
    ]
    analyzer = FakeAnalyzer([0.9, 0.85])  # both above the 0.8 target

    yielded = drive_concurrent_staining(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        stitcher=stitcher,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=slides,
    )

    assert opentrons.run_protocols == []
    assert len(stitcher.inputs) == 2  # each slide imaged exactly once
    assert len(yielded) == 4
    assert all("done" in m for m in captured_logs)


def test_state_tracks_each_slide_through_the_workflow(
    robot, opentrons, microscope, stitcher, segmenter, captured_logs
):
    """The injected AppState records every slide's final status, rounds and images."""
    state = AppState()
    slides = [
        Slide(name="s1", protocol="stain-A", trajectory="traj-1"),  # needs one round
        Slide(name="s2", protocol="stain-B", trajectory="traj-2"),  # already good
    ]
    # s1: under target then clears; s2: above target immediately.
    analyzer = FakeAnalyzer([0.1, 0.9, 0.9])

    drive_concurrent_staining(
        robot=robot,
        opentrons=opentrons,
        microscope=microscope,
        stitcher=stitcher,
        segmenter=segmenter,
        analyzer=analyzer,
        loaded_slides=slides,
        state=state,
    )

    # Both slides end DONE, and no slide is left mid-acquisition.
    assert dict(state.slide_status) == {
        "s1": SlideStatus.DONE,
        "s2": SlideStatus.DONE,
    }
    assert state.currently_imaging_slide is None
    # s1 went through one staining round; s2 needed none.
    assert state.staining_rounds["s1"] == 1
    assert state.staining_rounds["s2"] == 0
    # Latest stitched/segmented images are recorded for both slides.
    assert set(state.latest_images) == {"s1", "s2"}
    assert set(state.latest_segmented) == {"s1", "s2"}
    # s1's staining round and both completions were logged.
    assert any("staining" in m for m in captured_logs)
    assert sum("done" in m for m in captured_logs) == 2


def test_state_reports_in_progress_statuses_mid_run():
    """While a compute task is blocked, its slide shows ANALYZING and others QUEUED."""
    state = AppState()
    slides = [
        Slide(name="s1", protocol="stain-A", trajectory="traj-1"),
        Slide(name="s2", protocol="stain-B", trajectory="traj-2"),
    ]

    async def _run() -> None:
        # Block segmentation so the run cannot complete; inspect state mid-flight.
        gate = asyncio.Event()

        class BlockingSegmenter(FakeSegmenter):
            async def segment_image(self, image: Image) -> Image:
                await gate.wait()
                return await super().segment_image(image)

        agen = run_concurrent_staining(
            robot=FakeRobot(),
            opentrons=FakeOpentrons(),
            microscope=FakeMicroscope(),
            stitcher=FakeStitcher(),
            segmenter=BlockingSegmenter(),
            analyzer=FakeAnalyzer([0.9, 0.9]),
            state=state,
            loaded_slides=slides,
            microscope_trajectory="to_microscope",
            opentrons_trajectory="to_opentrons",
            tile_positions=["p1", "p2"],
        )
        # Drive the generator in the background; it will hang on the gated segmenter.
        consumer = asyncio.ensure_future(_drain(agen))
        await asyncio.sleep(0.05)  # let both slides get imaged and analysis start

        # Both slides have been imaged and handed off to (blocked) compute.
        assert state.slide_status["s1"] == SlideStatus.ANALYZING
        assert state.slide_status["s2"] == SlideStatus.ANALYZING
        assert state.currently_imaging_slide is None

        gate.set()  # release segmentation so the workflow can finish cleanly
        await asyncio.wait_for(consumer, timeout=2.0)

    async def _drain(agen) -> None:
        async for _ in agen:
            pass

    asyncio.run(_run())
    assert dict(state.slide_status) == {"s1": SlideStatus.DONE, "s2": SlideStatus.DONE}
