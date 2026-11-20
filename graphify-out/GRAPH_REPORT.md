# Graph Report - IndustryAI_Project  (2026-11-20)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 61 nodes · 21 edges · 40 communities (2 shown, 38 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.88)
- Token cost: 530 input · 461 output

## Graph Freshness
- Built from commit: `0af6ebf7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Inspection and Evidence Storage
- PCB Landmark Management
- Reference and Annotation Setup
- HCCB5 Component Data
- HCCC5 Component Data
- HCDC5 Component Data
- HDCC5 Component Data
- MBCC5 Component Data
- MCCB5 Component Data
- MCDC5 Component Data
- MDCC5 Component Data
- EBCC5 Component Data
- ECCB5 Component Data
- ECCC5 Component Data
- ECDC5 Component Data
- EDCC5 Component Data
- PCB Dataset Configuration
- Calibration Configuration
- Offline Inspection System
- Reporting and Evidence Review
- Operator User Interface
- FBCC5 Component Labels
- FCCB5 Component Labels
- FCCC5 Component Labels
- FDCC5 Component Labels
- KBCC5 Component Labels
- KCCB5 Component Labels
- KCCC5 Component Labels
- KDCC5 Component Labels
- ABCC5 Component Labels
- ACCB5 Component Labels
- ACCC5 Component Labels
- ACDC5 Component Labels
- ADCC5 Component Labels
- BBCC5 Component Labels
- BCCB5 Component Labels
- BCCC5 Component Labels
- BCDC5 Component Labels
- BDCC5 Component Labels
- HBCC5 Component Labels

## God Nodes (most connected - your core abstractions)
1. `3.0 Inspect each photo independently` - 3 edges
2. `Comparator` - 2 edges
3. `Landmark service` - 2 edges
4. `D3 Result and evidence store` - 1 edges
5. `2.0 Batch intake and snapshot` - 1 edges
6. `FR-10: Configurable Sharpening` - 1 edges
7. `D2 Local PCB landmark weights and schema` - 1 edges
8. `API and validation` - 1 edges
9. `MDCC5 Label` - 1 edges
10. `MDCC5 Photo` - 1 edges

## Surprising Connections (you probably didn't know these)
- `MDCC5 Label` --references--> `MDCC5 Photo`  [EXTRACTED]
  PCB_Dataset_Pilot/PCB_Dataset_Pilot/labels/train/MDCC5.txt → PCB_Dataset_Pilot/PCB_Dataset_Pilot/images/train/MDCC5.jpg
- `EBCC5 Label` --references--> `EBCC5 Photo`  [EXTRACTED]
  PCB_Dataset_Pilot/PCB_Dataset_Pilot/labels/val/EBCC5.txt → PCB_Dataset_Pilot/PCB_Dataset_Pilot/images/val/EBCC5.jpg
- `ECCB5 Label` --references--> `ECCB5 Photo`  [EXTRACTED]
  PCB_Dataset_Pilot/PCB_Dataset_Pilot/labels/val/ECCB5.txt → PCB_Dataset_Pilot/PCB_Dataset_Pilot/images/val/ECCB5.jpg
- `ECCC5 Label` --references--> `ECCC5 Photo`  [EXTRACTED]
  PCB_Dataset_Pilot/PCB_Dataset_Pilot/labels/val/ECCC5.txt → PCB_Dataset_Pilot/PCB_Dataset_Pilot/images/val/ECCC5.jpg
- `ECDC5 Label` --references--> `ECDC5 Photo`  [EXTRACTED]
  PCB_Dataset_Pilot/PCB_Dataset_Pilot/labels/val/ECDC5.txt → PCB_Dataset_Pilot/PCB_Dataset_Pilot/images/val/ECDC5.jpg

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **BeagleBone Black Dataset** — pcb_dataset_pilot_images_val_ebcc5, pcb_dataset_pilot_images_val_eccb5, pcb_dataset_pilot_images_val_eccc5, pcb_dataset_pilot_images_val_ecdc5, pcb_dataset_pilot_images_val_edcc5 [EXTRACTED 0.90]
- **Raspberry Pi Model A+ Dataset** — pcb_dataset_pilot_images_train_mbcc5, pcb_dataset_pilot_images_train_mccb5, pcb_dataset_pilot_images_train_mcdc5, pcb_dataset_pilot_images_train_mdcc5 [EXTRACTED 0.90]
- **Raspberry Pi Model B+ Dataset** — pcb_dataset_pilot_images_train_hccb5, pcb_dataset_pilot_images_train_hccc5, pcb_dataset_pilot_images_train_hcdc5, pcb_dataset_pilot_images_train_hdcc5 [EXTRACTED 0.90]
- **Inspection Pipeline Flow** — docs_dfd_p2, docs_dfd_p3, docs_dfd_p4 [EXTRACTED 1.00]
- **Landmark Detection Subsystem** — docs_sdd_landmark_service, docs_dfd_d2, pcb_dataset_pilot_pcb_dataset_pilot_dataset_yaml [INFERRED 0.80]

## Communities (40 total, 38 thin omitted)

### Community 0 - "Inspection and Evidence Storage"
Cohesion: 0.40
Nodes (5): D3 Result and evidence store, 2.0 Batch intake and snapshot, 3.0 Inspect each photo independently, Comparator, FR-10: Configurable Sharpening

### Community 1 - "PCB Landmark Management"
Cohesion: 0.67
Nodes (3): D2 Local PCB landmark weights and schema, API and validation, Landmark service

## Knowledge Gaps
- **58 isolated node(s):** `D3 Result and evidence store`, `2.0 Batch intake and snapshot`, `FR-10: Configurable Sharpening`, `D2 Local PCB landmark weights and schema`, `API and validation` (+53 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 58 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **38 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `D3 Result and evidence store`, `2.0 Batch intake and snapshot`, `FR-10: Configurable Sharpening` to the rest of the system?**
  _58 weakly-connected nodes found - possible documentation gaps or missing edges._