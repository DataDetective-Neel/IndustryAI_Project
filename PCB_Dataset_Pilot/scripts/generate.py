"""
PCB AOI Dataset Generator
Generates realistic, reproducible PCB inspection images with ground-truth annotations
from a golden reference PCB image.
Supports pilot mode (12 images) and full production mode (180 images).
"""

import os
import sys
import json
import csv
import argparse
import cv2
import numpy as np

GOLDEN_IMG_PATH = 'dataset_generation/golden/golden_reference.png'
GOLDEN_META_PATH = 'dataset_generation/golden/golden_components.json'

def load_golden():
    with open(GOLDEN_META_PATH, 'r') as f:
        meta = json.load(f)
    img = cv2.imread(GOLDEN_IMG_PATH)
    if img is None:
        raise FileNotFoundError(f"Could not load golden reference from {GOLDEN_IMG_PATH}")
    return img, meta

def draw_pad(canvas, x1, y1, x2, y2, trace_entry=None):
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    pw, ph = x2 - x1, y2 - y1

    copper_dark = (95, 68, 30)
    copper_light = (130, 95, 45)
    if trace_entry == 'left':
        cv2.line(canvas, (max(0, x1 - 16), (y1 + y2) // 2), (x1, (y1 + y2) // 2), copper_dark, 3)
        cv2.line(canvas, (max(0, x1 - 16), (y1 + y2) // 2), (x1, (y1 + y2) // 2), copper_light, 1)
    elif trace_entry == 'right':
        cv2.line(canvas, (x2, (y1 + y2) // 2), (min(canvas.shape[1], x2 + 16), (y1 + y2) // 2), copper_dark, 3)
        cv2.line(canvas, (x2, (y1 + y2) // 2), (min(canvas.shape[1], x2 + 16), (y1 + y2) // 2), copper_light, 1)
    elif trace_entry == 'top':
        cv2.line(canvas, ((x1 + x2) // 2, max(0, y1 - 16)), ((x1 + x2) // 2, y1), copper_dark, 3)
        cv2.line(canvas, ((x1 + x2) // 2, max(0, y1 - 16)), ((x1 + x2) // 2, y1), copper_light, 1)
    elif trace_entry == 'bottom':
        cv2.line(canvas, ((x1 + x2) // 2, y2), ((x1 + x2) // 2, min(canvas.shape[0], y2 + 16)), copper_dark, 3)
        cv2.line(canvas, ((x1 + x2) // 2, y2), ((x1 + x2) // 2, min(canvas.shape[0], y2 + 16)), copper_light, 1)

    cv2.rectangle(canvas, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (45, 35, 20), -1)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), (160, 165, 170), -1)

    for r in range(ph):
        frac = r / max(1, ph)
        val = int(220 - frac * 50)
        cv2.line(canvas, (x1 + 1, y1 + r), (x2 - 1, y1 + r), (val - 5, val, val + 5), 1)

    hl_w, hl_h = max(2, pw // 3), max(2, ph // 3)
    cv2.rectangle(canvas, (x1 + 2, y1 + 2), (x1 + 2 + hl_w, y1 + 2 + hl_h), (240, 245, 250), -1)

    noise = np.random.normal(0, 3.0, (ph, pw, 3)).astype(np.int16)
    patch = canvas[y1:y2, x1:x2].astype(np.int16) + noise
    canvas[y1:y2, x1:x2] = np.clip(patch, 0, 255).astype(np.uint8)

def blend_substrate_texture(canvas, x, y, w, h, golden_img):
    tex_sample = golden_img[350:450, 480:580].copy()
    tx = cv2.resize(tex_sample, (w, h), interpolation=cv2.INTER_LINEAR)

    margin = 8
    surr_y1, surr_y2 = max(0, y - margin), min(canvas.shape[0], y + h + margin)
    surr_x1, surr_x2 = max(0, x - margin), min(canvas.shape[1], x + w + margin)
    surr_crop = canvas[surr_y1:surr_y2, surr_x1:surr_x2]

    mask_surr = np.ones(surr_crop.shape[:2], dtype=bool)
    mask_surr[y - surr_y1 : y - surr_y1 + h, x - surr_x1 : x - surr_x1 + w] = False

    if np.any(mask_surr):
        local_mean = surr_crop[mask_surr].mean(axis=0)
    else:
        local_mean = np.array([105.0, 75.0, 35.0])

    tx_mean = tx.mean(axis=(0, 1))
    scale = local_mean / np.maximum(tx_mean, 1.0)
    tx_adjusted = np.clip(tx.astype(np.float32) * scale, 0, 255).astype(np.uint8)

    # Inpaint body strictly within component boundary
    body_mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
    cv2.rectangle(body_mask, (x + 2, y + 2), (x + w - 2, y + h - 2), 255, -1)
    inpainted = cv2.inpaint(canvas, body_mask, inpaintRadius=2, flags=cv2.INPAINT_TELEA)

    alpha = np.zeros((h, w), dtype=np.float32)
    alpha[2:-2, 2:-2] = 1.0
    alpha = cv2.GaussianBlur(alpha, (5, 5), 1.5)
    alpha_3d = np.repeat(alpha[:, :, np.newaxis], 3, axis=2)

    blended = tx_adjusted.astype(np.float32) * alpha_3d + inpainted[y:y+h, x:x+w].astype(np.float32) * (1.0 - alpha_3d)
    inpainted[y:y+h, x:x+w] = np.clip(blended, 0, 255).astype(np.uint8)

    return inpainted

def apply_missing_component(img, comp, golden_img, rng=None):
    x, y, w, h = comp['bbox']
    cx, cy = x + w // 2, y + h // 2
    footprint = comp.get('footprint', '')

    work = blend_substrate_texture(img, x, y, w, h, golden_img)
    silk_color = (215, 220, 225)

    if footprint == 'SMD_CAN_6.3mm':
        draw_pad(work, x + 6, cy - 13, x + 22, cy + 13, trace_entry='left')
        draw_pad(work, x + w - 22, cy - 13, x + w - 6, cy + 13, trace_entry='right')
        cv2.rectangle(work, (x + 4, y + 4), (x + w - 4, y + h - 4), silk_color, 1)
        cv2.line(work, (x + 10, cy - 20), (x + 18, cy - 20), silk_color, 1)
        cv2.line(work, (x + 14, cy - 24), (x + 14, cy - 16), silk_color, 1)

    elif footprint == 'HC-49SMD':
        draw_pad(work, cx - 14, y + 8, cx + 14, y + 26, trace_entry='top')
        draw_pad(work, cx - 14, y + h - 26, cx + 14, y + h - 8, trace_entry='bottom')
        cv2.rectangle(work, (x + 6, y + 30), (x + w - 6, y + h - 30), silk_color, 1)

    elif footprint == 'SOT-223':
        draw_pad(work, cx - 22, y + 6, cx + 22, y + 26, trace_entry='top')
        for px in [cx - 22, cx, cx + 22]:
            draw_pad(work, px - 6, y + h - 24, px + 6, y + h - 6, trace_entry='bottom')
        cv2.rectangle(work, (x + 4, y + 4), (x + w - 4, y + h - 4), silk_color, 1)

    elif footprint == 'SOIC-8':
        for i in range(4):
            py = y + 10 + i * 16
            draw_pad(work, x + 2, py - 4, x + 12, py + 4, trace_entry='left')
            draw_pad(work, x + w - 12, py - 4, x + w - 2, py + 4, trace_entry='right')
        cv2.circle(work, (x + 8, y - 4), 2, silk_color, -1)
        cv2.rectangle(work, (x + 14, y + 4), (x + w - 14, y + h - 4), silk_color, 1)

    elif footprint == 'TACT_6x6_SMD':
        pw, ph = 14, 12
        draw_pad(work, x + 4, y + 4, x + 4 + pw, y + 4 + ph, trace_entry='left')
        draw_pad(work, x + w - 4 - pw, y + 4, x + w - 4, y + 4 + ph, trace_entry='right')
        draw_pad(work, x + 4, y + h - 4 - ph, x + 4 + pw, y + h - 4, trace_entry='left')
        draw_pad(work, x + w - 4 - pw, y + h - 4 - ph, x + w - 4, y + h - 4, trace_entry='right')
        cv2.rectangle(work, (x + 10, y + 8), (x + w - 10, y + h - 8), silk_color, 1)
        cv2.circle(work, (cx, cy), 14, silk_color, 1)

    elif footprint in ('SMD_0805', 'SMD_0603', 'DO-214AC', 'SMD_1812'):
        if h >= w:
            pad_h = max(5, h // 5)
            draw_pad(work, x + 2, y + 2, x + w - 2, y + 2 + pad_h, trace_entry='top')
            draw_pad(work, x + 2, y + h - 2 - pad_h, x + w - 2, y + h - 2, trace_entry='bottom')
        else:
            pad_w = max(5, w // 5)
            draw_pad(work, x + 2, y + 2, x + 2 + pad_w, y + h - 2, trace_entry='left')
            draw_pad(work, x + w - 2 - pad_w, y + 2, x + w - 2, y + h - 2, trace_entry='right')
        cv2.rectangle(work, (x + 1, y + 1), (x + w - 1, y + h - 1), silk_color, 1)

    elif footprint == 'RES_NET_1206_4X':
        for i in range(4):
            py = y + 4 + i * 7
            draw_pad(work, x + 1, py, x + 8, py + 4, trace_entry='left')
            draw_pad(work, x + w - 8, py, x + w - 1, py + 4, trace_entry='right')
        cv2.rectangle(work, (x + 2, y + 2), (x + w - 2, y + h - 2), silk_color, 1)

    elif footprint == 'QFN-32':
        draw_pad(work, cx - 16, cy - 16, cx + 16, cy + 16, trace_entry=None)
        cv2.rectangle(work, (x + 3, y + 3), (x + w - 3, y + h - 3), silk_color, 1)

    else:
        draw_pad(work, x + 4, y + 4, x + w - 4, y + h - 4)
        cv2.rectangle(work, (x + 2, y + 2), (x + w - 2, y + h - 2), silk_color, 1)

    return work

def apply_misaligned_component(img, comp, dx, dy, d_theta, golden_img, rng=None):
    x, y, w, h = comp['bbox']
    comp_crop = golden_img[y:y+h, x:x+w].copy()

    base = apply_missing_component(img, comp, golden_img, rng=rng)

    pad_margin = 40
    patch_h, patch_w = h + 2 * pad_margin, w + 2 * pad_margin
    comp_rgba = np.zeros((patch_h, patch_w, 4), dtype=np.uint8)
    comp_rgba[pad_margin:pad_margin+h, pad_margin:pad_margin+w, :3] = comp_crop
    comp_rgba[pad_margin:pad_margin+h, pad_margin:pad_margin+w, 3] = 255

    alpha_blurred = cv2.GaussianBlur(comp_rgba[:, :, 3], (5, 5), 1.2)
    comp_rgba[:, :, 3] = alpha_blurred

    center = (patch_w / 2.0, patch_h / 2.0)
    M = cv2.getRotationMatrix2D(center, d_theta, 1.0)
    M[0, 2] += dx
    M[1, 2] += dy

    rotated_rgba = cv2.warpAffine(
        comp_rgba, M, (patch_w, patch_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0)
    )

    shadow_alpha = (rotated_rgba[:, :, 3].astype(float) / 255.0) * 0.35
    shadow_kernel = np.ones((5, 5), np.float32) / 25.0
    shadow_blurred = cv2.filter2D(shadow_alpha, -1, shadow_kernel)

    dest_x1 = x - pad_margin
    dest_y1 = y - pad_margin
    dest_x2 = dest_x1 + patch_w
    dest_y2 = dest_y1 + patch_h

    src_x1 = max(0, -dest_x1)
    src_y1 = max(0, -dest_y1)
    src_x2 = patch_w - max(0, dest_x2 - base.shape[1])
    src_y2 = patch_h - max(0, dest_y2 - base.shape[0])

    dest_x1 = max(0, dest_x1)
    dest_y1 = max(0, dest_y1)
    dest_x2 = min(base.shape[1], dest_x2)
    dest_y2 = min(base.shape[0], dest_y2)

    if dest_x2 > dest_x1 and dest_y2 > dest_y1:
        bg_crop = base[dest_y1:dest_y2, dest_x1:dest_x2].astype(float)
        sh_slice = shadow_blurred[src_y1:src_y2, src_x1:src_x2]
        sh_slice_3d = np.repeat(sh_slice[:, :, np.newaxis], 3, axis=2)
        bg_shadowed = bg_crop * (1.0 - sh_slice_3d * 0.7)

        comp_rgb = rotated_rgba[src_y1:src_y2, src_x1:src_x2, :3].astype(float)
        alpha = (rotated_rgba[src_y1:src_y2, src_x1:src_x2, 3].astype(float) / 255.0)
        alpha_3d = np.repeat(alpha[:, :, np.newaxis], 3, axis=2)

        blended = comp_rgb * alpha_3d + bg_shadowed * (1.0 - alpha_3d)
        base[dest_y1:dest_y2, dest_x1:dest_x2] = np.clip(blended, 0, 255).astype(np.uint8)

    corners = np.array([
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h]
    ], dtype=np.float32)

    comp_cx, comp_cy = x + w / 2.0, y + h / 2.0
    M_comp = cv2.getRotationMatrix2D((comp_cx, comp_cy), d_theta, 1.0)
    M_comp[0, 2] += dx
    M_comp[1, 2] += dy

    transformed_corners = cv2.transform(np.array([corners]), M_comp)[0]
    min_x = float(np.min(transformed_corners[:, 0]))
    min_y = float(np.min(transformed_corners[:, 1]))
    max_x = float(np.max(transformed_corners[:, 0]))
    max_y = float(np.max(transformed_corners[:, 1]))

    actual_bbox = [round(min_x, 2), round(min_y, 2), round(max_x - min_x, 2), round(max_y - min_y, 2)]
    actual_corners = [[round(pt[0], 2), round(pt[1], 2)] for pt in transformed_corners]

    return base, actual_bbox, actual_corners

def apply_board_transform(img, board_rot_deg, board_dx, board_dy, exposure_scale, brightness_offset, color_temp, noise_sigma, rng=None):
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)

    M = cv2.getRotationMatrix2D(center, board_rot_deg, 1.0)
    M[0, 2] += board_dx
    M[1, 2] += board_dy

    transformed_img = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )

    img_float = transformed_img.astype(np.float32) * exposure_scale + brightness_offset

    img_float[:, :, 0] *= color_temp[0]
    img_float[:, :, 1] *= color_temp[1]
    img_float[:, :, 2] *= color_temp[2]

    if noise_sigma > 0:
        if rng is not None:
            noise = rng.normal(0, noise_sigma, img.shape).astype(np.float32)
        else:
            noise = np.random.normal(0, noise_sigma, img.shape).astype(np.float32)
        img_float += noise

    final_img = np.clip(img_float, 0, 255).astype(np.uint8)
    return final_img, M

def transform_bbox_with_board(bbox, M):
    x, y, w, h = bbox
    corners = np.array([
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h]
    ], dtype=np.float32)

    transformed_corners = cv2.transform(np.array([corners]), M)[0]
    min_x = float(np.min(transformed_corners[:, 0]))
    min_y = float(np.min(transformed_corners[:, 1]))
    max_x = float(np.max(transformed_corners[:, 0]))
    max_y = float(np.max(transformed_corners[:, 1]))

    out_bbox = [round(min_x, 2), round(min_y, 2), round(max_x - min_x, 2), round(max_y - min_y, 2)]
    out_corners = [[round(pt[0], 2), round(pt[1], 2)] for pt in transformed_corners]
    return out_bbox, out_corners

def build_full_configs(golden_meta):
    """
    Builds the deterministic configuration list for exactly 180 images:
    - 90 GOOD
    - 35 MISSING_COMPONENT
    - 35 MISALIGNED_COMPONENT
    - 20 MULTIPLE_DEFECTS
    """
    removable = [c['id'] for c in golden_meta['components'] if c.get('removable', False)]
    misalignable = [c['id'] for c in golden_meta['components'] if c.get('misalignable', False)]

    configs = []

    # 1. 90 GOOD images (good_001 to good_090)
    for i in range(1, 91):
        seed = 1000 + i
        rng = np.random.RandomState(seed)
        rot = round(float(rng.uniform(-1.4, 1.4)), 3)
        dx = round(float(rng.uniform(-7.5, 7.5)), 2)
        dy = round(float(rng.uniform(-7.5, 7.5)), 2)
        exp = round(float(rng.uniform(0.95, 1.04)), 3)
        br = round(float(rng.uniform(-5.0, 5.0)), 2)
        ct = [
            round(float(rng.uniform(0.985, 1.015)), 3),
            1.00,
            round(float(rng.uniform(0.985, 1.015)), 3)
        ]
        noise = round(float(rng.uniform(0.8, 1.6)), 2)

        configs.append({
            'image_id': f'good_{i:03d}',
            'defect_category': 'GOOD',
            'subfolder': 'good',
            'seed': seed,
            'board_rot': rot,
            'board_dx': dx,
            'board_dy': dy,
            'exposure': exp,
            'brightness': br,
            'color_temp': ct,
            'noise': noise,
            'defects': []
        })

    # 2. 35 MISSING_COMPONENT images (missing_001 to missing_035)
    for i in range(1, 36):
        seed = 2000 + i
        rng = np.random.RandomState(seed)
        target_comp = removable[(i - 1) % len(removable)]

        rot = round(float(rng.uniform(-1.2, 1.2)), 3)
        dx = round(float(rng.uniform(-6.0, 6.0)), 2)
        dy = round(float(rng.uniform(-6.0, 6.0)), 2)
        exp = round(float(rng.uniform(0.96, 1.03)), 3)
        br = round(float(rng.uniform(-4.0, 4.0)), 2)
        ct = [round(float(rng.uniform(0.99, 1.01)), 3), 1.0, round(float(rng.uniform(0.99, 1.01)), 3)]
        noise = round(float(rng.uniform(1.0, 1.5)), 2)

        configs.append({
            'image_id': f'missing_{i:03d}',
            'defect_category': 'MISSING_COMPONENT',
            'subfolder': 'missing',
            'seed': seed,
            'board_rot': rot,
            'board_dx': dx,
            'board_dy': dy,
            'exposure': exp,
            'brightness': br,
            'color_temp': ct,
            'noise': noise,
            'defects': [{'type': 'missing', 'comp_id': target_comp}]
        })

    # 3. 35 MISALIGNED_COMPONENT images (misaligned_001 to misaligned_035)
    for i in range(1, 36):
        seed = 3000 + i
        rng = np.random.RandomState(seed)
        target_comp = misalignable[(i - 1) % len(misalignable)]

        # Scale displacement to physical component size:
        # Large components (cans, ICs, crystals, switches) handle 7-14px.
        # Small 0805 passives/LEDs handle 3-6px to avoid colliding with neighbors.
        comp_bbox = [c['bbox'] for c in golden_meta['components'] if c['id'] == target_comp][0]
        if comp_bbox[2] < 45 or comp_bbox[3] < 45:
            disp_x = round(float(rng.choice([-1, 1]) * rng.uniform(3.0, 6.0)), 2)
            disp_y = round(float(rng.choice([-1, 1]) * rng.uniform(3.0, 6.0)), 2)
            d_th = round(float(rng.choice([-1, 1]) * rng.uniform(6.0, 14.0)), 2)
        else:
            disp_x = round(float(rng.choice([-1, 1]) * rng.uniform(7.0, 14.0)), 2)
            disp_y = round(float(rng.choice([-1, 1]) * rng.uniform(6.0, 13.0)), 2)
            d_th = round(float(rng.choice([-1, 1]) * rng.uniform(9.0, 20.0)), 2)

        # SMT clearance steering: avoid displacing into immediately adjacent packages
        if target_comp == 'RN1':
            disp_x = -abs(disp_x)
        elif target_comp == 'LED_L':
            disp_x = abs(disp_x)
        elif target_comp == 'LED_TX':
            disp_x = -abs(disp_x)
        elif target_comp == 'LED_RX':
            disp_x = abs(disp_x)
        elif target_comp in ('C3', 'C4'):
            disp_y = -abs(disp_y)
        elif target_comp in ('C5', 'C6'):
            disp_y = abs(disp_y)
        elif target_comp == 'R1':
            disp_y = abs(disp_y)
        elif target_comp == 'LED_ON':
            disp_y = -abs(disp_y)

        rot = round(float(rng.uniform(-1.2, 1.2)), 3)
        dx = round(float(rng.uniform(-6.0, 6.0)), 2)
        dy = round(float(rng.uniform(-6.0, 6.0)), 2)
        exp = round(float(rng.uniform(0.96, 1.03)), 3)
        br = round(float(rng.uniform(-4.0, 4.0)), 2)
        ct = [round(float(rng.uniform(0.99, 1.01)), 3), 1.0, round(float(rng.uniform(0.99, 1.01)), 3)]
        noise = round(float(rng.uniform(1.0, 1.5)), 2)

        configs.append({
            'image_id': f'misaligned_{i:03d}',
            'defect_category': 'MISALIGNED_COMPONENT',
            'subfolder': 'misaligned',
            'seed': seed,
            'board_rot': rot,
            'board_dx': dx,
            'board_dy': dy,
            'exposure': exp,
            'brightness': br,
            'color_temp': ct,
            'noise': noise,
            'defects': [{'type': 'misaligned', 'comp_id': target_comp, 'dx': disp_x, 'dy': disp_y, 'd_theta': d_th}]
        })

    # 4. 20 MULTIPLE_DEFECTS images (multiple_defects_001 to multiple_defects_020)
    for i in range(1, 21):
        seed = 4000 + i
        rng = np.random.RandomState(seed)

        # Select 2 distinct components
        comp_m = removable[(i * 3) % len(removable)]
        comp_s = misalignable[(i * 3 + 2) % len(misalignable)]
        if comp_m == comp_s:
            comp_s = misalignable[(i * 3 + 5) % len(misalignable)]

        comp_bbox_s = [c['bbox'] for c in golden_meta['components'] if c['id'] == comp_s][0]
        if comp_bbox_s[2] < 45 or comp_bbox_s[3] < 45:
            disp_x = round(float(rng.choice([-1, 1]) * rng.uniform(3.0, 6.0)), 2)
            disp_y = round(float(rng.choice([-1, 1]) * rng.uniform(3.0, 6.0)), 2)
            d_th = round(float(rng.choice([-1, 1]) * rng.uniform(7.0, 14.0)), 2)
        else:
            disp_x = round(float(rng.choice([-1, 1]) * rng.uniform(7.0, 13.0)), 2)
            disp_y = round(float(rng.choice([-1, 1]) * rng.uniform(6.0, 12.0)), 2)
            d_th = round(float(rng.choice([-1, 1]) * rng.uniform(9.0, 18.0)), 2)

        # SMT clearance steering: avoid displacing into immediately adjacent packages
        if comp_s == 'RN1':
            disp_x = -abs(disp_x)
        elif comp_s == 'LED_L':
            disp_x = abs(disp_x)
        elif comp_s == 'LED_TX':
            disp_x = -abs(disp_x)
        elif comp_s == 'LED_RX':
            disp_x = abs(disp_x)
        elif comp_s in ('C3', 'C4'):
            disp_y = -abs(disp_y)
        elif comp_s in ('C5', 'C6'):
            disp_y = abs(disp_y)
        elif comp_s == 'R1':
            disp_y = abs(disp_y)
        elif comp_s == 'LED_ON':
            disp_y = -abs(disp_y)

        rot = round(float(rng.uniform(-1.2, 1.2)), 3)
        dx = round(float(rng.uniform(-6.0, 6.0)), 2)
        dy = round(float(rng.uniform(-6.0, 6.0)), 2)
        exp = round(float(rng.uniform(0.96, 1.03)), 3)
        br = round(float(rng.uniform(-4.0, 4.0)), 2)
        ct = [round(float(rng.uniform(0.99, 1.01)), 3), 1.0, round(float(rng.uniform(0.99, 1.01)), 3)]
        noise = round(float(rng.uniform(1.0, 1.5)), 2)

        configs.append({
            'image_id': f'multiple_defects_{i:03d}',
            'defect_category': 'MULTIPLE_DEFECTS',
            'subfolder': 'multiple_defects',
            'seed': seed,
            'board_rot': rot,
            'board_dx': dx,
            'board_dy': dy,
            'exposure': exp,
            'brightness': br,
            'color_temp': ct,
            'noise': noise,
            'defects': [
                {'type': 'missing', 'comp_id': comp_m},
                {'type': 'misaligned', 'comp_id': comp_s, 'dx': disp_x, 'dy': disp_y, 'd_theta': d_th}
            ]
        })

    return configs

def execute_generation(configs, mode='full'):
    golden_img, golden_meta = load_golden()
    comps_by_id = {c['id']: c for c in golden_meta['components']}

    records = []
    total = len(configs)
    print(f"Starting dataset generation in [{mode.upper()}] mode: {total} images...")

    for idx, cfg in enumerate(configs, start=1):
        img_id = cfg['image_id']
        cat = cfg['defect_category']
        subfolder = cfg['subfolder']
        seed = cfg['seed']
        rng = np.random.RandomState(seed)

        work_img = golden_img.copy()

        affected_ids = []
        missing_ids = []
        displacement_map = {}
        rotation_map = {}
        pre_board_actual_bboxes = {}

        for c in golden_meta['components']:
            cid = c['id']
            pre_board_actual_bboxes[cid] = list(c['bbox'])
            displacement_map[cid] = [0.0, 0.0]
            rotation_map[cid] = 0.0

        for d in cfg['defects']:
            cid = d['comp_id']
            comp = comps_by_id[cid]
            affected_ids.append(cid)

            if d['type'] == 'missing':
                missing_ids.append(cid)
                work_img = apply_missing_component(work_img, comp, golden_img, rng=rng)
                pre_board_actual_bboxes[cid] = None
                displacement_map[cid] = [0.0, 0.0]
                rotation_map[cid] = 0.0

            elif d['type'] == 'misaligned':
                dx = d['dx']
                dy = d['dy']
                d_theta = d['d_theta']
                work_img, act_bbox, act_corners = apply_misaligned_component(
                    work_img, comp, dx, dy, d_theta, golden_img, rng=rng
                )
                pre_board_actual_bboxes[cid] = act_bbox
                displacement_map[cid] = [round(dx, 2), round(dy, 2)]
                rotation_map[cid] = round(d_theta, 2)

        final_img, M_board = apply_board_transform(
            work_img,
            cfg['board_rot'],
            cfg['board_dx'],
            cfg['board_dy'],
            cfg['exposure'],
            cfg['brightness'],
            cfg['color_temp'],
            cfg['noise'],
            rng=rng
        )

        expected_bboxes = {}
        actual_bboxes = {}

        for c in golden_meta['components']:
            cid = c['id']
            exp_bbox, _ = transform_bbox_with_board(c['bbox'], M_board)
            expected_bboxes[cid] = exp_bbox

            if cid in missing_ids:
                actual_bboxes[cid] = None
            else:
                pre_act = pre_board_actual_bboxes[cid]
                act_bbox, _ = transform_bbox_with_board(pre_act, M_board)
                actual_bboxes[cid] = act_bbox

        img_filename = f"{img_id}.png"
        img_rel_path = os.path.join('dataset_generation', 'images', subfolder, img_filename)
        cv2.imwrite(img_rel_path, final_img)

        anno_data = {
            'image_id': img_id,
            'file_name': img_filename,
            'image_path': f"images/{subfolder}/{img_filename}",
            'reference_image_id': 'golden_reference.png',
            'board_id': f"ELEGOO_MEGA2560_{img_id.upper()}",
            'defect_category': cat,
            'affected_component_ids': affected_ids,
            'expected_component_bboxes': expected_bboxes,
            'actual_component_bboxes': actual_bboxes,
            'missing_component_ids': missing_ids,
            'displacement_pixels': {k: v for k, v in displacement_map.items() if k in affected_ids},
            'rotation_degrees': {k: v for k, v in rotation_map.items() if k in affected_ids},
            'board_transform': {
                'rotation_degrees': round(cfg['board_rot'], 3),
                'translation_pixels': [round(cfg['board_dx'], 2), round(cfg['board_dy'], 2)],
                'exposure_scale': round(cfg['exposure'], 3),
                'brightness_offset': round(cfg['brightness'], 2),
                'affine_matrix': [[round(val, 5) for val in row] for row in M_board.tolist()]
            },
            'generation_seed': seed
        }

        anno_filename = f"{img_id}.json"
        anno_rel_path = os.path.join('dataset_generation', 'annotations', anno_filename)
        with open(anno_rel_path, 'w') as f:
            json.dump(anno_data, f, indent=2)

        records.append({
            'image_id': img_id,
            'file_name': img_filename,
            'category': cat,
            'subfolder': subfolder,
            'affected_components': ';'.join(affected_ids) if affected_ids else 'NONE',
            'missing_components': ';'.join(missing_ids) if missing_ids else 'NONE',
            'board_rotation_deg': cfg['board_rot'],
            'board_dx_px': cfg['board_dx'],
            'board_dy_px': cfg['board_dy'],
            'seed': seed,
            'annotation_file': f"annotations/{anno_filename}"
        })

        if idx % 20 == 0 or idx == total:
            print(f"[{idx}/{total}] Processed {img_id} ({cat})")

    csv_path = 'dataset_generation/metadata.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'image_id', 'file_name', 'category', 'subfolder',
            'affected_components', 'missing_components',
            'board_rotation_deg', 'board_dx_px', 'board_dy_px',
            'seed', 'annotation_file'
        ])
        writer.writeheader()
        writer.writerows(records)

    print(f"Successfully generated {len(records)} images and saved {csv_path}.")

def create_splits(records):
    """
    Creates leakage-prevented development and held-out evaluation manifests (70% dev, 30% eval).
    """
    by_cat = {}
    for r in records:
        cat = r['category']
        by_cat.setdefault(cat, []).append(r['image_id'])

    dev_ids = []
    eval_ids = []

    for cat, ids in by_cat.items():
        # Deterministic split ratio: 70% dev, 30% eval
        n_eval = max(1, int(len(ids) * 0.30))
        # Keep pilot images in dev where appropriate
        eval_slice = ids[-n_eval:]
        dev_slice = ids[:-n_eval]
        dev_ids.extend(dev_slice)
        eval_ids.extend(eval_slice)

    dev_manifest = {
        'split': 'development',
        'count': len(dev_ids),
        'image_ids': dev_ids
    }
    eval_manifest = {
        'split': 'held_out_evaluation',
        'count': len(eval_ids),
        'image_ids': eval_ids
    }

    with open('dataset_generation/splits/dev_manifest.json', 'w') as f:
        json.dump(dev_manifest, f, indent=2)
    with open('dataset_generation/splits/eval_manifest.json', 'w') as f:
        json.dump(eval_manifest, f, indent=2)

    print(f"Splits created: Dev={len(dev_ids)}, Eval={len(eval_ids)} (Total={len(dev_ids)+len(eval_ids)})")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['pilot', 'full'], default='full', help='pilot (12 images) or full (180 images)')
    args = parser.parse_args()

    golden_img, golden_meta = load_golden()
    if args.mode == 'pilot':
        # Use first 4 Good, 3 Missing, 3 Misaligned, 2 Multi
        all_cfgs = build_full_configs(golden_meta)
        pilot_cfgs = (
            [c for c in all_cfgs if c['defect_category'] == 'GOOD'][:4] +
            [c for c in all_cfgs if c['defect_category'] == 'MISSING_COMPONENT'][:3] +
            [c for c in all_cfgs if c['defect_category'] == 'MISALIGNED_COMPONENT'][:3] +
            [c for c in all_cfgs if c['defect_category'] == 'MULTIPLE_DEFECTS'][:2]
        )
        execute_generation(pilot_cfgs, mode='pilot')
    else:
        full_cfgs = build_full_configs(golden_meta)
        execute_generation(full_cfgs, mode='full')
        # Load generated metadata records to produce splits
        with open('dataset_generation/metadata.csv', 'r') as f:
            recs = list(csv.DictReader(f))
        create_splits(recs)
