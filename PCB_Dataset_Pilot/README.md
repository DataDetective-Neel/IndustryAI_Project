# PCB inspection pilot dataset

The pilot contains 32 real photos across seven source layout IDs. Its immediate
purpose is to exercise four-landmark labels, board alignment, and inspection
of regions whose components are present. It is small enough to inspect and use
for a training smoke test. The landmark labels are initial annotations with
manual placement and visual checks of feature-projected points.

| Split | Photos | Source layout IDs |
|---|---:|---|
| Train | 19 | A, B, H, M |
| Validation | 5 | E |
| Test | 8 | F, K |

All views of a source layout stay in the same split. Similar-looking board
families stay together too. The split above is specific to this project. Source
layout letters are used as IDs, since some example photos and model names in the
source README appear inconsistent. Three requested files did not download as
valid images and were omitted.

## Files

- `dataset.yaml` defines a single class, `pcb`, with four 3-value keypoints.
- `images/{train,val,test}` contains JPEGs with longest side at most 1536 pixels.
- `labels/{train,val,test}` contains matching YOLO Pose text files.
- `manifest.csv` gives provenance, split, dimensions, and annotation method.
- `inspection_controls.json` provides one test reference, two named component
  boxes in that reference, and three real photos of the same board. Both marked
  components are visible in all three photos.
- `landmark_preview.jpg` shows the four landmarks on one image per layout.

## Four landmark labels

The keypoint order is upper left, upper right, lower right, and lower left.
These are physical mounting-hole centers defined in a layout's canonical
orientation. Keep each identity attached to the same hole as the board rotates.
Use one board box per image, followed by four normalized x, y, visibility
triples. Included landmarks are visible and have visibility 2. Use a separate
test when you collect a photo with a blocked or cropped landmark.

Run the first YOLO smoke test with flipping disabled (`fliplr=0.0 flipud=0.0`).
This keeps physical landmark identities consistent on these asymmetric PCBs.
Pass the extracted `dataset.yaml` by absolute path as the training data config.
Use the held-out test photos after training and tuning are complete.

## Missing-part data to collect next

Build matched sets by board layout and side. For each selected layout, take a
known-good reference and photos of the same layout with confirmed missing parts.
Record the affected component IDs on each photo. Keep source and augmented
versions of the same photo in the same split. Separate edited smoke-test
examples from real defective captures when reporting performance.

PCB-MC is a candidate source for annotated missing footprints. Verify that any
images used here have a matching known-good reference for that exact layout and
component configuration.

## Source and redistribution

Photos and source board boxes are from **micro-PCB Images**, Adam Byerly
(frettapper), Kaggle dataset version 2, under Creative Commons Attribution 4.0.
This subset selects and resizes the photos and adds four mounting-hole labels,
dataset splits, and inspection control annotations.

- Source dataset. https://www.kaggle.com/datasets/frettapper/micropcb-images
- Photo license. https://creativecommons.org/licenses/by/4.0/
- YOLO pose format. https://docs.ultralytics.com/datasets/pose/
- PCB-MC dataset. https://doi.org/10.4121/7c6e5bda-eecf-4feb-8a3a-7f823b1b0140
