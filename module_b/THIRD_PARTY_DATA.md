# Module B third-party training data

## MoLa-VI Dataset, version 1

- Title: **MoLa-VI Dataset**
- Authors: Sandra Dixe, João Leite, Sahar Azadi, Jaime Fonseca, and João Borges
- Publisher: Mendeley Data
- Published: 2021-11-24
- DOI: <https://doi.org/10.17632/cfsr5kvry3.1>
- Source: <https://data.mendeley.com/datasets/cfsr5kvry3/1>
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)

Module B uses the RGB vehicle-interior images and their pixel masks to train an
experimental cleanliness model. The original mask values are reduced to these
internal targets:

| Original value | Original class | Module B target |
|---:|---|---|
| 4 | `STAIN` | `stain` |
| 5 | `DIRT` | `dirt` |
| 0, 1, 2, 3, 6 | unlabelled, damage, or `GOOD` | `background` |

This mapping does not claim that damage is clean. It only means that damage is
not a positive target for the independent cleanliness model.

The original archives, extracted images, masks, generated manifests, and
training splits are local-only data under `data/` and are not committed. The
official archive hashes used to verify the download are recorded in
`module_b/data_sources/mola_vi_v1.json`.

The model and documentation must retain this attribution, a link to the CC BY
4.0 license, and a note that the class mapping and model fine-tuning are
modifications made by the Hotai iRent AI Prototype team.
