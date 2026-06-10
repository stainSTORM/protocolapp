# 🌩️ StainStorm

**StainStorm** is an [arkitekt-next](https://arkitekt.live) *meta-app* for automated
histological staining. It doesn't drive any hardware itself — it **coordinates** a fleet
of other arkitekt apps into end-to-end imaging-and-staining workflows:

- a **robot arm** that moves slides between the tray, microscope and Opentrons,
- a **microscope** that acquires images,
- an **Opentrons** liquid handler that runs staining/washing protocols,
- a **stitcher** and a **Cellpose** segmenter that turn tiles into labelled cells,
- an **analyzer** that measures how stained each sample is.

The whole app lives in a single file: [`app.py`](app.py).

---

## What it does

You load a set of slides (each with a staining protocol and a tray position) and
StainStorm runs them through one of two workflows. As each slide is processed, its
progress is published as live state (`queued → imaging → analyzing → staining → done`),
so you can watch the run unfold.

### `run_stainstorm` — wash loop

Image and segment each slide, measure its stain, and while it's **over-stained** send it
to the Opentrons for a washing step and re-image — repeating until it's clean enough or a
maximum number of rounds is reached. One slide at a time.

### `run_concurrent_staining` — concurrent staining ⭐

The same idea, but optimized: while the robot is busy moving the next slide, the
stitching, segmentation and analysis of earlier slides run in the background. When a
slide's analysis comes back **under**-stained (too few stained cells), it's sent to the
Opentrons to be stained and then re-imaged — up to a maximum number of rounds. Slides are
imaged one at a time (there's only one microscope), but the heavy compute happens in
parallel across the fleet, so many slides are in flight at once.

---

## Getting started

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                  # install
uv run python app.py     # connect to arkitekt and register the workflows
```

The coordinated apps (robot, microscope, Opentrons, stitcher, Cellpose, analyzer) must be
connected to the same arkitekt instance for a workflow to run end to end.

> ⚠️ The `analyzer` app identifier in `app.py` is still a placeholder — set it to the real
> analyzer app once it's available.

---

## Testing

```bash
uv run pytest
```

The workflows are tested with local stand-ins for each coordinated app, so no hardware or
network is needed.
