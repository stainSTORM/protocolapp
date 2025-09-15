# The StainStorm Protocol

This repository contains the implementation of the StainStorm protocol, designed for the analysis of histological images. The protocol includes steps for image acquisition, cell segmentation, and quantification of stained cells and serves as a meta app that will call other apps to perform these tasks.

## Scope

To main functions are provided:

- "smart_logic_loop": This function implements a loop that iteratively acquires images, segments cells, and calculates the percentage of stained cells. It continues this process until a specified maximum number of iterations is reached or a target staining percentage is achieved.

- "graphed_smart_logic_loop": This function extends the capabilities of "smart_logic_loop" by constructing a kraph "knowledge graph" that captures the relationships between the various steps in the protocol. This graph can be used for visualization and further analysis of the workflow.



