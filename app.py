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
from mikro_next.api.schema import (
    Image,
    from_array_like,
    PartialInstanceMaskViewInput,
    create_reference_view,
)
from arkitekt_next import easy, register, log
import numpy as np


@register
def move_robot_slide_holder():
    # Implement robot movement logic here
    print("Moving robot slide holder")
    return


@register
def grip_slide_holder():
    # Implement robot movement logic here
    log("Gripping slide holder")
    return


@register
def release_slide_holder():
    # Implement robot movement logic here
    log("Releasing slide holder")
    return


@register
def pick_up_slide_in_tray(slider: int):
    # Implement robot movement logic here
    log(f"Picking up slide {slider} in tray")
    return


@register
def drop_slider_in_tray(slider: int):
    # Implement robot movement logic here
    log(f"Dropping slide {slider} in tray")
    # Implement robot movement logic here
    return


@register
def move_robot_to_microscope():
    # Implement robot movement logic here
    log("Moving robot to microscope")
    return


@register
def segment_cells(image: Image) -> Image:
    # Implement cell segmentation logic here
    log("Segmenting cells")
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
    log("Moving robot to Opentrons")
    return


@register
def drop_slide():
    # Implement robot movement logic here
    log("Dropping slide")
    return


@register
def pickup_slide():
    # Implement robot movement logic here
    log("Picking up slide")
    return


@register
def acquire_image() -> Image:
    # Implement image acquisition logic here
    log("Acquiring image")
    return from_array_like(
        np.random.randint(0, 256, (1, 100, 100), dtype=np.uint8), name="Acquired Image"
    )


@register
def run_washing_protocol():
    # Implement staining protocol logic here
    log("Running staining protocol")
    return


@register(
    dependencies=[
        acquire_image,
        segment_cells,
        calculate_percentage_of_stained_cells,
        move_robot_to_opentrons,
        drop_slide,
        pickup_slide,
        move_robot_to_microscope,
        grip_slide_holder,
        move_robot_slide_holder,
        release_slide_holder,
        pick_up_slide_in_tray,
        drop_slider_in_tray,
        run_washing_protocol,
    ]
)
def smart_logic_loop(max_iterations=5):
    num_sliders = 1

    for slider in range(num_sliders):
        move_robot_slide_holder()
        pick_up_slide_in_tray(slider)  # Use the current slider index
        grip_slide_holder()

        move_robot_to_microscope()
        release_slide_holder()

        # Run initial acquisition and segmentation
        image = acquire_image()
        iteration = 0
        segmented_image = segment_cells(image)
        current_stain_percentage = calculate_percentage_of_stained_cells(
            segmented_image
        )

        while current_stain_percentage > 0.8 and iteration < max_iterations:
            pickup_slide()
            move_robot_to_opentrons()
            drop_slide()

            run_washing_protocol()

            pickup_slide()
            move_robot_to_microscope()
            drop_slide()

            image = acquire_image()
            segmented_image = segment_cells(image)
            current_stain_percentage = calculate_percentage_of_stained_cells(
                segmented_image
            )

            iteration += 1
            log(
                f"Iteration {iteration}, Stain Percentage: {current_stain_percentage:.2%}"
            )

        if iteration == max_iterations:
            log("Reached maximum iterations without sufficient staining.")

        pickup_slide()
        move_robot_slide_holder()
        drop_slider_in_tray(slider)

    return


@register(
    dependencies=[
        acquire_image,
        segment_cells,
        calculate_percentage_of_stained_cells,
        move_robot_to_opentrons,
        drop_slide,
        pickup_slide,
        move_robot_to_microscope,
        grip_slide_holder,
        move_robot_slide_holder,
        release_slide_holder,
        pick_up_slide_in_tray,
        drop_slider_in_tray,
        run_washing_protocol,
    ]
)
def graphed_smart_logic_loop(graph_name="StainStorm Graph", max_iterations=5):
    num_sliders = 5

    graph = create_graph(name=graph_name, description="Graph for StainStorm protocol")

    # Define categories and protocols
    # Our subject is a biological sample on a slide
    Sample = create_entity_category(
        label="Sample", description="A biological sample on a slide", graph=graph
    )

    # Measurement Categories describe what kind of measurements we are taking
    # to monitor the staining process
    ACQUISITION_FOR = create_measurement_category(
        label="Acquisition of",
        description="The image is a microscopic acquisition of a sample",
        graph=graph,
        structure_definition=Image,
        entity_definition=Sample,
    )

    LABELMASK_FOR = create_measurement_category(
        label="Labelmask for",
        description="The image is a segmentation mask labeling stained cells in a sample as well as unstained cells",
        graph=graph,
        structure_definition=Image,
        entity_definition=Sample,
    )

    # Protocol Event Categories describe the events in our protocol
    # Each washing step is an event with a duration and associated slide
    WASHING_STEP = create_protocol_event_category(
        graph=graph,
        label="OpenTrons Washing Step",
        description="Event representing a washing step performed by the OpenTrons robot",
        variable_definitions=[
            VariableDefinitionInput(
                param="duration",
                valueKind=MetricKind.FLOAT,
                description="Duration of the washing step in minutes",
            )
        ],
        source_entity_roles=[
            EntityRoleDefinitionInput(
                role="slide",
                description="The slide being processed",
                label="Slide",
                categoryDefinition=Sample,
            )
        ],
    )

    # Create samples for each slide
    loaded_samples = [Sample(name=f"Sample {i + 1}") for i in range(num_sliders)]

    for slider, sample in enumerate(loaded_samples):
        move_robot_slide_holder()
        pick_up_slide_in_tray(slider)  # Use the current slider index
        grip_slide_holder()

        move_robot_to_microscope()
        release_slide_holder()

        # Run initial acquisition and segmentation
        image = acquire_image()
        image | ACQUISITION_FOR() | sample

        iteration = 0
        segmented_image = segment_cells(image)

        current_stain_percentage = calculate_percentage_of_stained_cells(
            segmented_image
        )

        segmented_image | LABELMASK_FOR() | sample

        create_structure_metric(
            structure=segmented_image,
            label="stain_percentage",
            value=current_stain_percentage,
            graph=graph,
            metric_kind=MetricKind.FLOAT,
        )

        while current_stain_percentage > 0.2 and iteration < max_iterations:
            pickup_slide()
            move_robot_to_opentrons()
            drop_slide()

            run_washing_protocol()
            washing_event = WASHING_STEP(slide=sample, duration=15.0)

            pickup_slide()
            move_robot_to_microscope()
            drop_slide()

            image = acquire_image()
            image | ACQUISITION_FOR() | sample
            segmented_image = segment_cells(image)
            segmented_image | LABELMASK_FOR() | sample
            current_stain_percentage = calculate_percentage_of_stained_cells(
                segmented_image
            )

            create_structure_metric(
                structure=segmented_image,
                label="stain_percentage",
                value=current_stain_percentage,
                graph=graph,
                metric_kind=MetricKind.FLOAT,
            )

            iteration += 1
            log(
                f"Iteration {iteration}, Stain Percentage: {current_stain_percentage:.2%}"
            )

        pickup_slide()
        move_robot_slide_holder()
        drop_slider_in_tray(slider)

    return


if __name__ == "__main__":
    with easy() as e:
        e.rekuest.run()
