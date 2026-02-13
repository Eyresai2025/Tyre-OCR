import os
import json
import cv2
import numpy as np
import pandas as pd

import sys

if len(sys.argv) > 1:
    BASE_INPUT_DIR = sys.argv[1]
else:
    raise ValueError("❌ INPUT_DIR not provided to apo_restich.py")

IMAGES_FOLDER = BASE_INPUT_DIR
MAPPING_FOLDER = os.path.join(BASE_INPUT_DIR, "cropped_boxes")
OCR_FOLDER = os.path.join(BASE_INPUT_DIR, "cropped_boxes", "output")
STITCHED_FOLDER = os.path.join(BASE_INPUT_DIR, "stitched")

os.makedirs(STITCHED_FOLDER, exist_ok=True)


os.makedirs(STITCHED_FOLDER, exist_ok=True)

print("🧵 Restitching OCR text into words and lines...")

# =========================
# GROUPING FUNCTION
# =========================
def group_by_line_and_gap(crops, y_thresh=50, min_x_gap=120, scale_gap=2.5):
    """
    Groups OCR crops into proper words/lines using
    vertical alignment + dynamic horizontal gap.
    """

    annotated = []
    for crop in crops:
        box = np.array(crop["box"], dtype=np.int32)
        x, y, w, h = cv2.boundingRect(box)
        annotated.append((x, y, w, h, crop["text"], box))

    # Sort top → bottom
    annotated.sort(key=lambda b: b[1])

    # ---- Group by text line ----
    rows, current_row = [], []
    for item in annotated:
        if not current_row:
            current_row.append(item)
        else:
            _, y0, _, _, *_ = current_row[0]
            _, y1, _, _, *_ = item
            if abs(y1 - y0) <= y_thresh:
                current_row.append(item)
            else:
                rows.append(current_row)
                current_row = [item]
    if current_row:
        rows.append(current_row)

    # ---- Merge words inside each line ----
    final_groups = []

    for row in rows:
        row.sort(key=lambda b: b[0])  # left → right

        avg_char_width = np.mean([
            w / max(len(text), 1) for x, y, w, h, text, _ in row
        ])
        x_gap_thresh = max(min_x_gap, int(avg_char_width * scale_gap))

        group, prev_x, prev_w = [], None, None

        for item in row:
            x, y, w, h, text, box = item
            if prev_x is None:
                group = [item]
            else:
                gap = x - (prev_x + prev_w)
                if gap <= x_gap_thresh:
                    group.append(item)
                else:
                    final_groups.append(group)
                    group = [item]
            prev_x, prev_w = x, w

        if group:
            final_groups.append(group)

    return final_groups

# =========================
# MAIN PROCESS
# =========================

excel_rows = []

for file in os.listdir(MAPPING_FOLDER):
    if not file.endswith("_mapping.json"):
        continue

    base_name = file.replace("_mapping.json", "")
    mapping_path = os.path.join(MAPPING_FOLDER, file)
    image_path = None
    for ext in (".jpg", ".png", ".jpeg"):
        p = os.path.join(IMAGES_FOLDER, base_name + ext)
        if os.path.exists(p):
            image_path = p
            break

    if image_path is None:
        print(f"⚠️ Missing image for {base_name}")
        continue

    if not os.path.exists(image_path):
        print(f"⚠️ Missing image: {image_path}")
        continue

    image = cv2.imread(image_path)

    with open(mapping_path, "r") as jf:
        mapping = json.load(jf)

    valid_crops = []

    for crop in mapping["crops"]:
        crop_file = crop["file"]
        ocr_json = os.path.join(
            OCR_FOLDER,
            f"{os.path.splitext(crop_file)[0]}_ocr.json"
        )

        if not os.path.exists(ocr_json):
            continue

        with open(ocr_json, "r") as ojf:
            ocr_data = json.load(ojf)

        texts = []

        if isinstance(ocr_data, list):
            for item in ocr_data:
                t = item.get("text", "").strip()   # ← FIXED HERE
                if t:
                    texts.append(t)

        elif isinstance(ocr_data, dict):
            t = ocr_data.get("text", "").strip()  # ← FIXED HERE
            if t:
                texts.append(t)

        for text in texts:
            valid_crops.append({
                "box": crop["box"],
                "text": text
            })



    # ---- Group and restitch ----
    groups = group_by_line_and_gap(valid_crops)
    if not valid_crops:
        continue

    # ---- Draw stitched text ----
    for group in groups:
        boxes = [item[5] for item in group]
        texts = [item[4] for item in group]

        all_pts = np.vstack(boxes).astype(np.int32)
        x, y, w, h = cv2.boundingRect(all_pts)

        merged_text = " ".join(texts)

        excel_rows.append({
            "image": base_name,
            "text": merged_text,
            # "x": int(x),
            # "y": int(y),
            # "w": int(w),
            # "h": int(h)
        })

        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
 
        # === USE EXACT SAME TEXT AS EXCEL ===
        text_to_draw = merged_text

        # Font scale from box height
        font_scale = max(0.4, min(1.0, h / 30))
        thickness = 2

        # Measure text
        (text_w, text_h), _ = cv2.getTextSize(
            text_to_draw,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness
        )

        # Ensure text fits inside box width
        if text_w > w - 6:
            font_scale *= (w - 6) / text_w
            (text_w, text_h), _ = cv2.getTextSize(
                text_to_draw,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                thickness
            )

        # Center text INSIDE bounding box
        text_x = x + max(2, (w - text_w) // 2)
        text_y = y + max(text_h + 2, (h + text_h) // 2)

        # Draw text INSIDE box
        cv2.putText(
            image,
            text_to_draw,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (0, 0, 255),
            thickness,
            cv2.LINE_AA
        )

    out_img = os.path.join(STITCHED_FOLDER, base_name + "_stitched.jpg")
    cv2.imwrite(out_img, image)
    print(f"✅ Saved stitched image: {out_img}")

# =========================
# SAVE EXCEL
# =========================
if excel_rows:
    df = pd.DataFrame(excel_rows)
    excel_path = os.path.join(STITCHED_FOLDER, "stitched_output.xlsx")
    df.to_excel(excel_path, index=False)
    print(f"📊 Excel saved: {excel_path}")
else:
    print("⚠️ No text found, Excel not created")


print("🎉 Restitching completed.")
