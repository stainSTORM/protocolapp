from enum import Enum
from pydantic import ConfigDict, BaseModel, Field
from typing import List, Optional, Literal
from rath.scalars import ID
from mikro_next.rath import MikroNextRath
from mikro_next.funcs import aexecute, execute


class PutIntoDatasetMutationPutimagesindataset(BaseModel):
    """No documentation"""

    typename: Literal["Dataset"] = Field(
        alias="__typename", default="Dataset", exclude=True
    )
    id: ID
    model_config = ConfigDict(frozen=True)


class PutIntoDatasetMutation(BaseModel):
    """No documentation found for this operation."""

    put_images_in_dataset: PutIntoDatasetMutationPutimagesindataset = Field(
        alias="putImagesInDataset"
    )
    "Add images to a dataset"

    class Arguments(BaseModel):
        """Arguments for PutIntoDataset"""

        images: List[ID]
        dataset_id: ID = Field(alias="datasetId")
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for PutIntoDataset"""

        document = "mutation PutIntoDataset($images: [ID!]!, $datasetId: ID!) {\n  putImagesInDataset(input: {selfs: $images, other: $datasetId}) {\n    id\n    __typename\n  }\n}"


async def aput_into_dataset(
    images: List[ID], dataset_id: ID, rath: Optional[MikroNextRath] = None
) -> PutIntoDatasetMutationPutimagesindataset:
    """PutIntoDataset

    Add images to a dataset

    Args:
        images (List[ID]): No description
        dataset_id (ID): No description
        rath (mikro_next.rath.MikroNextRath, optional): The mikro rath client

    Returns:
        PutIntoDatasetMutationPutimagesindataset
    """
    return (
        await aexecute(
            PutIntoDatasetMutation,
            {"images": images, "datasetId": dataset_id},
            rath=rath,
        )
    ).put_images_in_dataset


def put_into_dataset(
    images: List[ID], dataset_id: ID, rath: Optional[MikroNextRath] = None
) -> PutIntoDatasetMutationPutimagesindataset:
    """PutIntoDataset

    Add images to a dataset

    Args:
        images (List[ID]): No description
        dataset_id (ID): No description
        rath (mikro_next.rath.MikroNextRath, optional): The mikro rath client

    Returns:
        PutIntoDatasetMutationPutimagesindataset
    """
    return execute(
        PutIntoDatasetMutation, {"images": images, "datasetId": dataset_id}, rath=rath
    ).put_images_in_dataset
