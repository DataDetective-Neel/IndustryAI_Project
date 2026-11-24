# Realistic PCB AOI Dataset Generator

Industrial Automated Optical Inspection (AOI) Synthetic Dataset Generator and Validation Engine.  
Designed for sub-millimeter defect detection, component presence/absence verification, and surface-mount technology (SMT) misalignment classification on the **ELEGOO MEGA 2560 R3** architecture.

---

## 1. Directory Structure

```
dataset_generation/
├── golden/
│   ├── golden_reference.png       # Original top-down reference photograph (969 x 1024)
│   ├── golden_annotated.png       # Annotated reference image with 34 verified components
│   └── golden_components.json     # Machine-readable component catalog and coordinates
├── images/
│   ├── good/                      # Nominal boards with fixture jitter and lighting drift
│   │   ├── good_001.png
│   │   ├── good_002.png
│   │   ├── good_003.png
│   │   └── good_004.png
│   ├── missing/                   # Realistically depopulated components with exposed pads
│   │   ├── missing_001.png        # Missing C1 (47uF SMD Electrolytic Can)
│   │   ├── missing_002.png        # Missing Y1 (16MHz HC-49SM Crystal)
│   │   └── missing_003.png        # Missing U3 (AMS1117 SOT-223 Voltage Regulator)
│   ├── misaligned/                # Skewed/displaced components with exposed solder pads
│   │   ├── misaligned_001.png     # Misaligned C2 (+14px, +12px, +15.0°)
│   │   ├── misaligned_002.png     # Misaligned U4 (-8px, -6px, -18.0°)
│   │   └── misaligned_003.png     # Misaligned SW1 (+15px, -10px, +12.0°)
│   └── multiple_defects/          # Multi-fault boards
│       ├── multiple_defects_001.png # Missing C1 + Misaligned Y1 (+10px, +8px, -14.0°)
│       └── multiple_defects_002.png # Missing U3 + Misaligned C2 (-12px, +10px, +16.0°)
├── annotations/                   # Per-image ground truth JSON files
│   ├── good_001.json ... multiple_defects_002.json
├── contact_sheets/
│   └── pilot_12_contact_sheet.png # 12-image visual validation contact sheet (1280 x 1080)
├── splits/
│   ├── pilot_dev.json             # Development split manifest (8 images)
│   └── pilot_eval.json            # Evaluation split manifest (4 images)
├── scripts/
│   ├── generate.py                # Deterministic synthetic image and annotation generator
│   └── validate.py                # Registration, SSIM, and schema validation suite
├── metadata.csv                   # Flat index of all generated pilot images and defects
├── dataset_summary.json           # Quantitative validation metrics and status
└── README.md                      # Comprehensive project documentation
```

---

## 2. Phase 1 — Golden PCB Analysis

- **Image Resolution**: $969 \times 1024$ pixels, 24-bit sRGB, top-down orthographic perspective.
- **Sharpness Metric**: Laplacian variance = **1897.99** (crisp, high-contrast SMT edge definitions).
- **PCB Substrate**: Double-sided blue solder mask with white silkscreen markings and ENIG / HASL tinned pads.
- **Component Catalogue**: Exactly **34 discrete components** mapped and bounded:
  - **Integrated Circuits (4)**: `U1` (ATmega2560 TQFP-100), `U2` (ATmega16U2 QFN-32), `U3` (AMS1117 SOT-223), `U4` (LM358 SOIC-8).
  - **Oscillator (1)**: `Y1` (16.000 MHz HC-49SMD crystal).
  - **Electrolytic SMD Capacitors (2)**: `C1`, `C2` ($47\mu\text{F}$ 25V SMD aluminum cans).
  - **Tactile Switches (1)**: `SW1` (Momentary reset pushbutton with red circular actuator).
  - **Diodes & Fuses (2)**: `D1` (SMA Schottky diode), `F1` (1812 polyfuse).
  - **LED Indicators (4)**: `LED_ON` (Power green), `LED_L` (Pin 13 yellow), `LED_TX`, `LED_RX` (Serial communications).
  - **Ceramic Passives & Arrays (7)**: `C3`, `C4`, `C5`, `C6`, `C7` (0805/0603 caps), `RN1`, `RN2` (4x convex resistor networks), `R1` (0805 resistor).
  - **Connectors & Pin Headers (13)**: `J1` (DC power barrel), `J2` (USB Type-B), `J3` (2x3 ICSP), `J4` (2x3 USB ICSP), `J5` (JP5 2x2 pads), `J_PWR`, `J_ANALOG1`, `J_ANALOG2`, `J_DIGITAL_HIGH`, `J_DIGITAL_MID`, `J_COMM`, `J_DIGITAL_BOTTOM` (2x18 double-row).

---

## 3. Defect Modeling Methodology

### Realistic Component Depopulation (Missing Defect)
Unlike naive rectangular inpainting that leaves blurry patches:
1. **Substrate Restoration**: Navier-Stokes / Telea inpainting blends surrounding blue solder mask texture and micro-grain into the component interior.
2. **Footprint Pad Synthesis**: Renders physical tinned solder pads (`[175, 180, 185]` base with `[225, 230, 235]` specular highlights), simulating reflowed solder meniscus.
3. **Silkscreen Preservation**: Reconstructs crisp white silkscreen outlines, polarity indicators, and pin 1 index marks.

### Geometric Component Misalignment
SMT pick-and-place skew and tombstoning effects:
1. **Underlying Footprint**: Synthesizes the original bare solder pads on the base board.
2. **Patch Isolation**: Isolates the component with a feathered 3px alpha boundary.
3. **In-Plane Kinematics**: Translates by $(\Delta x, \Delta y)$ and rotates by $\Delta \theta$ around the component center.
4. **Lighting-Consistent Cast Shadow**: Renders directional contact shadow (+2px X, +3px Y, 35% opacity) matching the overhead illuminator.
5. **Partial Pad Occlusion**: The misaligned part partially covers the pads while leaving opposite pads exposed, matching real microscope imagery.

### Whole-Board Conveyor Dynamics
To simulate industrial conveyor and jig placement jitter:
- Translation: $\Delta X, \Delta Y \in [-6.0, +8.5]$ pixels.
- In-Plane Rotation: $\theta \in [-0.90^\circ, +1.20^\circ]$.
- Border Mode: Reflection and edge replication to avoid black frame borders.
- Illumination Drift: Exposure factor $1.00 \pm 0.04$, brightness offset $[-5, +4]$ DN, subtle color temperature variations, and sensor Gaussian noise ($\sigma \in [1.0, 1.8]$).

---

## 4. Ground-Truth Annotation Schema

Each inspection image is accompanied by an eponymous JSON file in `dataset_generation/annotations/`:

```json
{
  "image_id": "misaligned_001",
  "file_name": "misaligned_001.png",
  "image_path": "images/misaligned/misaligned_001.png",
  "reference_image_id": "golden_reference.png",
  "board_id": "ELEGOO_MEGA2560_MISALIGNED_001",
  "defect_category": "MISALIGNED_COMPONENT",
  "affected_component_ids": ["C2"],
  "expected_component_bboxes": {
    "C2": [232.84, 281.33, 82.26, 77.89],
    "U1": [386.95, 451.34, 229.87, 230.12]
  },
  "actual_component_bboxes": {
    "C2": [243.61, 290.45, 96.34, 94.12],
    "U1": [386.95, 451.34, 229.87, 230.12]
  },
  "missing_component_ids": [],
  "displacement_pixels": {
    "C2": [14.0, 12.0]
  },
  "rotation_degrees": {
    "C2": 15.0
  },
  "board_transform": {
    "rotation_degrees": -0.5,
    "translation_pixels": [-2.0, 3.0],
    "exposure_scale": 1.0,
    "brightness_offset": 0.0,
    "affine_matrix": [[0.99996, 0.00873, -4.218], [-0.00873, 0.99996, 7.228]]
  },
  "generation_seed": 3001
}
```

---

## 5. Validation Results (Pilot Suite)

The pilot was evaluated using `dataset_generation/scripts/validate.py`:

| Check Category | Metric | Achieved Value | Threshold / Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Integrity** | Image dimensions | $969 \times 1024 \times 3$ | Match Golden Reference | **PASS** |
| **Registration** | ORB Inlier Ratio | **96.4%** | $\ge 80.0\%$ | **PASS** |
| **Alignment** | Reprojection Error | **0.90 px** | $\le 2.0\text{ px}$ (Sub-pixel) | **PASS** |
| **Fidelity** | Aligned SSIM with Golden | **0.9457** | $\ge 0.9000$ | **PASS** |
| **Good Boards** | Defect Count | **0 false defects** | Exactly 0 | **PASS** |
| **Defect Localization** | Expected vs Actual BBox | Exact coordinate tracking | Match physical transforms | **PASS** |
| **Unaffected Components** | Coordinate drift | **0 px drift** | Unaffected $B_{actual} == B_{expected}$ | **PASS** |

---

## 6. Generalization Limits Notice

> [!WARNING]
> All 12 pilot images (and any future derivatives) originate from a single golden PCB reference (`ELEGOO MEGA 2560 R3`). While photorealistic variations in lighting, sensor noise, conveyor jitter, and defect configurations are introduced, **this dataset does not establish generalization to unseen PCB layout topologies, alternate solder mask colors (green, red, black), or uncharacterized component form-factors**.
