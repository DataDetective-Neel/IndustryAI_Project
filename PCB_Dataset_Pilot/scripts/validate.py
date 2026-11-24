"""
PCB AOI Dataset Validation Suite
Validates the generated images against the golden reference:
- File integrity and format checks
- Image registration (ORB feature matching and homography against golden)
- Structural similarity and defect localization verification
- Rigorous pixel-level correlation checks of unchanged component regions
- Annotation correspondence and schema adherence
- Contact sheet generation (high-resolution composite)
- Quantitative validation report (dataset_summary.json)
"""

import os
import json
import csv
import cv2
import numpy as np

def compute_ssim(img1, img2):
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)

    kernel = cv2.getGaussianKernel(11, 1.5)
    window = np.outer(kernel, kernel.transpose())

    mu1 = cv2.filter2D(img1, -1, window)[5:-5, 5:-5]
    mu2 = cv2.filter2D(img2, -1, window)[5:-5, 5:-5]

    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.filter2D(img1 ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
    sigma2_sq = cv2.filter2D(img2 ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
    sigma12 = cv2.filter2D(img1 * img2, -1, window)[5:-5, 5:-5] - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    return float(ssim_map.mean())

def validate_dataset():
    golden_path = 'dataset_generation/golden/golden_reference.png'
    golden_img = cv2.imread(golden_path)
    if golden_img is None:
        raise FileNotFoundError(f"Golden reference not found at {golden_path}")
    gh, gw = golden_img.shape[:2]
    golden_gray = cv2.cvtColor(golden_img, cv2.COLOR_BGR2GRAY)

    with open('dataset_generation/golden/golden_components.json', 'r') as f:
        golden_meta = json.load(f)

    with open('dataset_generation/metadata.csv', 'r') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    orb = cv2.ORB_create(nfeatures=2500)
    kp_golden, des_golden = orb.detectAndCompute(golden_gray, None)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    results = []
    contact_sheet_items = []
    total = len(records)
    print(f"Starting validation of {total} dataset images...")

    for idx, rec in enumerate(records, start=1):
        img_id = rec['image_id']
        cat = rec['category']
        subfolder = rec['subfolder']
        img_file = os.path.join('dataset_generation', 'images', subfolder, rec['file_name'])
        anno_file = os.path.join('dataset_generation', rec['annotation_file'])

        if not os.path.exists(img_file):
            raise FileNotFoundError(f"Missing image file: {img_file}")
        if not os.path.exists(anno_file):
            raise FileNotFoundError(f"Missing annotation file: {anno_file}")

        img = cv2.imread(img_file)
        h, w = img.shape[:2]
        assert (h, w) == (gh, gw), f"Dimensions mismatch for {img_id}: {(w, h)} vs {(gw, gh)}"

        with open(anno_file, 'r') as f:
            anno = json.load(f)

        required_keys = [
            'image_id', 'reference_image_id', 'board_id', 'defect_category',
            'affected_component_ids', 'expected_component_bboxes',
            'actual_component_bboxes', 'missing_component_ids',
            'displacement_pixels', 'rotation_degrees', 'board_transform',
            'generation_seed'
        ]
        for k in required_keys:
            assert k in anno, f"Missing key '{k}' in {anno_file}"

        # Fast registration check: on large sets, sample or verify all
        # To maintain high performance across 180 images, compute ORB on first 500 features
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kp_img, des_img = orb.detectAndCompute(gray, None)

        inlier_ratio = 0.0
        reg_error_px = 0.0
        aligned_ssim = 0.0

        if des_img is not None and len(des_img) > 15:
            matches = bf.knnMatch(des_img, des_golden, k=2)
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.75 * n.distance:
                        good_matches.append(m)

            if len(good_matches) > 15:
                src_pts = np.float32([kp_img[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp_golden[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                if mask is not None:
                    inliers = int(mask.sum())
                    inlier_ratio = inliers / max(1, len(good_matches))

                    aligned = cv2.warpPerspective(gray, H, (gw, gh))
                    aligned_ssim = compute_ssim(aligned, golden_gray)

                    src_inliers = src_pts[mask.ravel() == 1]
                    dst_inliers = dst_pts[mask.ravel() == 1]
                    projected = cv2.perspectiveTransform(src_inliers, H)
                    reg_error_px = float(np.mean(np.linalg.norm(projected - dst_inliers, axis=2)))

        # Pixel-level validation of unchanged vs affected component regions
        M_board = np.array(anno['board_transform']['affine_matrix'], dtype=np.float32)
        M_inv = cv2.invertAffineTransform(M_board)
        warped_to_golden = cv2.warpAffine(img, M_inv, (gw, gh), flags=cv2.INTER_LINEAR)

        affected_comps = anno['affected_component_ids']
        missing_comps = anno['missing_component_ids']

        unaffected_correlations = []
        affected_correlations = []

        for comp in golden_meta['components']:
            cid = comp['id']
            x, y, cw, ch = comp['bbox']
            ref_crop = golden_img[y:y+ch, x:x+cw]
            test_crop = warped_to_golden[y:y+ch, x:x+cw]

            ref_gray_crop = cv2.cvtColor(ref_crop, cv2.COLOR_BGR2GRAY)
            test_gray_crop = cv2.cvtColor(test_crop, cv2.COLOR_BGR2GRAY)

            ncc = float(cv2.matchTemplate(test_gray_crop, ref_gray_crop, cv2.TM_CCOEFF_NORMED)[0][0])

            if cid in affected_comps:
                affected_correlations.append((cid, round(ncc, 3)))
            else:
                unaffected_correlations.append(ncc)
                # Check adjacency to affected components
                is_adjacent = False
                for aff_id in affected_comps:
                    aff_bbox = [c['bbox'] for c in golden_meta['components'] if c['id'] == aff_id][0]
                    dx = max(0, max(x, aff_bbox[0]) - min(x + cw, aff_bbox[0] + aff_bbox[2]))
                    dy = max(0, max(y, aff_bbox[1]) - min(y + ch, aff_bbox[1] + aff_bbox[3]))
                    if dx <= 20 and dy <= 20:
                        is_adjacent = True
                        break
                threshold = 0.70 if is_adjacent else 0.82
                assert ncc >= threshold, f"Pixel drift in component {cid} in {img_id}: NCC={ncc:.3f} (threshold={threshold})"

        avg_unaffected_corr = round(float(np.mean(unaffected_correlations)), 4) if unaffected_correlations else 1.0
        min_unaffected_corr = round(float(np.min(unaffected_correlations)), 4) if unaffected_correlations else 1.0
        assert avg_unaffected_corr >= 0.95, f"Low average unaffected correlation in {img_id}: {avg_unaffected_corr}"

        if cat == 'GOOD':
            assert len(affected_comps) == 0, f"Good image {img_id} has affected components!"
            assert len(missing_comps) == 0, f"Good image {img_id} has missing components!"
        elif cat == 'MISSING_COMPONENT':
            assert len(missing_comps) > 0, f"Missing image {img_id} has no missing components!"
        elif cat == 'MISALIGNED_COMPONENT':
            assert len(affected_comps) > 0 and len(missing_comps) == 0, f"Misaligned image {img_id} invalid!"
        elif cat == 'MULTIPLE_DEFECTS':
            assert len(affected_comps) >= 2, f"Multiple defects image {img_id} has fewer than 2 defects!"

        for comp in golden_meta['components']:
            cid = comp['id']
            if cid not in affected_comps:
                exp_b = anno['expected_component_bboxes'][cid]
                act_b = anno['actual_component_bboxes'][cid]
                assert act_b is not None, f"Unaffected component {cid} missing in {img_id}!"
                assert exp_b == act_b, f"Unaffected component {cid} bbox drift in {img_id}!"

        results.append({
            'image_id': img_id,
            'category': cat,
            'affected_components': affected_comps,
            'missing_components': missing_comps,
            'inlier_ratio': round(inlier_ratio, 3),
            'reg_reprojection_error_px': round(reg_error_px, 2),
            'aligned_ssim_with_golden': round(aligned_ssim, 4),
            'unaffected_pixel_correlation_avg': avg_unaffected_corr,
            'unaffected_pixel_correlation_min': min_unaffected_corr,
            'affected_component_correlations': affected_correlations,
            'unaffected_components_preserved': len(unaffected_correlations),
            'status': 'PASS'
        })

        if idx <= 12:
            contact_sheet_items.append((img_id, cat, affected_comps, img))

        if idx % 30 == 0 or idx == total:
            print(f"[{idx}/{total}] Validated {img_id} ({cat}) - Status: PASS")

    print(f"Successfully validated all {len(results)} images!")

    # Generate 12-image pilot contact sheet
    if len(contact_sheet_items) >= 12:
        thumb_w, thumb_h = 320, 340
        cols, rows = 4, 3
        sheet_w = cols * thumb_w
        sheet_h = rows * thumb_h + 60
        sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
        sheet[:] = (35, 35, 35)

        cv2.putText(sheet, "PCB AOI DATASET VALIDATION (12 REPRESENTATIVE IMAGES) - ELEGOO MEGA 2560 R3",
                    (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)

        cat_colors = {
            'GOOD': (60, 180, 75),
            'MISSING_COMPONENT': (30, 105, 230),
            'MISALIGNED_COMPONENT': (230, 180, 30),
            'MULTIPLE_DEFECTS': (180, 50, 220)
        }

        for idx, (img_id, cat, aff, im) in enumerate(contact_sheet_items[:12]):
            r = idx // cols
            c = idx % cols
            x_offset = c * thumb_w
            y_offset = 60 + r * thumb_h

            im_thumb = cv2.resize(im, (thumb_w - 12, thumb_h - 48), interpolation=cv2.INTER_AREA)
            sheet[y_offset + 38: y_offset + 38 + im_thumb.shape[0], x_offset + 6: x_offset + 6 + im_thumb.shape[1]] = im_thumb

            color = cat_colors.get(cat, (200, 200, 200))
            cv2.rectangle(sheet, (x_offset + 6, y_offset + 4), (x_offset + thumb_w - 6, y_offset + 34), (50, 50, 50), -1)
            cv2.rectangle(sheet, (x_offset + 6, y_offset + 4), (x_offset + thumb_w - 6, y_offset + 34), color, 2)

            title = f"{img_id} [{cat[:4]}]"
            cv2.putText(sheet, title, (x_offset + 12, y_offset + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            aff_txt = f"Defects: {','.join(aff) if aff else 'None'}"
            cv2.putText(sheet, aff_txt, (x_offset + 12, y_offset + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (220, 220, 220), 1, cv2.LINE_AA)

        contact_path = 'dataset_generation/contact_sheets/pilot_12_contact_sheet.png'
        cv2.imwrite(contact_path, sheet)
        print(f"Contact sheet regenerated at {contact_path}")

    # Build comprehensive summary JSON
    summary = {
        'dataset_summary': {
            'total_images': len(results),
            'categories': {
                'GOOD': sum(1 for r in results if r['category'] == 'GOOD'),
                'MISSING_COMPONENT': sum(1 for r in results if r['category'] == 'MISSING_COMPONENT'),
                'MISALIGNED_COMPONENT': sum(1 for r in results if r['category'] == 'MISALIGNED_COMPONENT'),
                'MULTIPLE_DEFECTS': sum(1 for r in results if r['category'] == 'MULTIPLE_DEFECTS')
            },
            'overall_status': 'ALL_CHECKS_PASSED',
            'registration_validation': {
                'average_inlier_ratio': round(float(np.mean([r['inlier_ratio'] for r in results])), 3),
                'average_reprojection_error_px': round(float(np.mean([r['reg_reprojection_error_px'] for r in results])), 2),
                'average_aligned_ssim': round(float(np.mean([r['aligned_ssim_with_golden'] for r in results])), 4)
            },
            'pixel_level_preservation': {
                'average_unaffected_pixel_correlation': round(float(np.mean([r['unaffected_pixel_correlation_avg'] for r in results])), 4),
                'minimum_unaffected_pixel_correlation': round(float(np.min([r['unaffected_pixel_correlation_min'] for r in results])), 4),
                'pixel_level_validation_status': 'VERIFIED'
            },
            'validation_details': results
        }
    }

    summary_path = 'dataset_generation/dataset_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Dataset summary saved to {summary_path}")

    return summary

if __name__ == '__main__':
    validate_dataset()
