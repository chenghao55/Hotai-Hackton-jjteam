# Module B third-party data record

Module B condition training accepts only sources whose manifest contains a
complete license record. Raw images, downloaded archives, generated manifests,
and checkpoints remain local and are excluded from Git.

## Approved damage source

| Field | Value |
|---|---|
| Dataset | Car Parts and Car Damages Dataset |
| Creator | Humans in the Loop |
| Source | https://humansintheloop.org/resources/datasets/car-parts-and-car-damages-dataset/ |
| License | CC0 1.0 Universal |
| License text | https://creativecommons.org/publicdomain/zero/1.0/ |
| Intended labels | Scratch; Dent; Cracked; Broken part; Missing part |
| Local mapping | Scratch → `scratch`; the other four → `collision_damage` |
| Retrieved | 2026-09-20 from the official Humans in the Loop Kaggle account |
| Kaggle version | Version 2 |
| Archive size | 3,103,430,533 bytes |
| Archive SHA-256 | `B7454257AA2AA08A7EA42003F8C1F15DB70E5D77D63567A4373414AE8A998577` |

The source page states that the dataset is dedicated to the public domain under
CC0 1.0. Record the actual download date and archive/version identifier in the
private training manifest. CC0 does not require attribution, but this record is
retained for traceability.

### Local audit result

The official v2 archive contains 1,812 image/annotation pairs in Supervisely
JSON format. Its two top-level directory names are reversed relative to the
annotation taxonomies, and 440 images occur byte-for-byte in both the part and
damage exports. The importer selects collections using annotation `classTitle`
values and excludes the part-only collection because missing damage labels there
mean "not annotated", not "no damage".

The resulting HITL-only manifest has 814 unique damage-annotated images:

| Image-level targets | Count |
|---|---:|
| neither selected target | 3 |
| `collision_damage` only | 294 |
| `scratch` only | 12 |
| both targets | 505 |

This provides 517 scratch positives and 297 scratch negatives, but only 15
collision negatives against 799 positives. HITL v2 alone is therefore not an
adequate basis for a reliable `collision_damage` image classifier. A later
approved dataset must add clearly annotated non-collision examples; part-only
polygons and iRent claim/no-claim labels must not be relabelled as category
negatives.

## Cleanliness source: approval required

No cleanliness dataset is approved merely by this repository. Before creating a
three-class checkpoint, the selected dataset must have all of the following:

- the original author or organization;
- the original source URL and a stable version or download identifier;
- a page explicitly granting CC0 1.0 or CC BY 4.0 to the dataset images;
- a license URL and a separate URL or archived record showing the license claim;
- a retrieval date; and
- `clean/` and `dirty/` labels whose meaning matches visible vehicle dirt,
  stains, litter, or similar cleaning needs.

For CC BY 4.0, keep author, title, source URL, license link, and a statement that
the images were resized, augmented, and used to fine-tune model weights. A
platform label with no traceable original source is insufficient. The manifest
loader rejects incomplete records, unknown licenses, missing images, and
conflicting duplicate labels.

Example source metadata file (values must describe the audited source):

```json
{
  "id": "publisher-dataset-version",
  "title": "Dataset title",
  "creator": "Original creator",
  "source_url": "https://original.example/dataset",
  "license": "CC-BY-4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "license_evidence_url": "https://original.example/dataset/license",
  "version": "stable version or archive checksum",
  "retrieved_at": "YYYY-MM-DD"
}
```

## Prohibited or unapproved inputs

- The unlabeled official iRent images are not supervised training data.
- CarDD-derived collections are not accepted without separate written
  authorization compatible with the intended use.
- Web search results, scraped images, and re-uploaded platform datasets with an
  unclear provenance chain are not accepted.

## Candidate audit (2026-09-20)

The following candidates were investigated and are **not approved** for the
training manifest:

| Candidate | Useful content | Decision |
|---|---|---|
| SOCAR / FMDC | 10,000 real car-sharing images, including exterior normal, damage, dirt, and dirty-interior classes | Best domain match, but the official access form currently returns “file does not exist.” The paper describes academic use and the website footer licenses site content, not clearly the dataset images. No dataset-level CC0 or CC BY 4.0 grant was found. |
| Roboflow “Clean or Dirty car” | 656 detection images, platform page marked CC BY 4.0 | Rejected because the uploader is identified only as “Detection,” with no original creator, collection method, or upstream image provenance. |
| Roboflow “clean-dirty car” | 127 classification images, platform page marked CC BY 4.0 | Rejected because the uploader is identified only as “test,” there is no dataset description, and no upstream provenance is provided. |
| HumynLabs `car-images` | 538 vehicle images, Hugging Face card marked CC BY 4.0 | Rejected as category-negative data because the card gives no damage/cleanliness labels or evidence that each image is undamaged and clean. |
| Wikimedia Commons categories | Dirty automobiles and damaged automobiles, with per-file license metadata | Not accepted as a ready dataset: licenses vary per file, category membership is weak supervision, the dirty class is small, and there is no equivalent audited clean-car control set. A curated subset would require per-file license filtering and label review. |

SOCAR remains the preferred source if its authors provide a working download
and explicit reuse terms compatible with this project. Contacting the authors or
submitting a replacement access form is an external communication and requires
separate user approval before it is done on the user's behalf.
