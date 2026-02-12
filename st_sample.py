import os
import json
import torch
import torch.backends.cudnn as cudnn
import numpy as np
import cv2
from collections import OrderedDict
from torch.autograd import Variable

import craft_utils
import imgproc
from craft import CRAFT
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================
# PATHS (EDIT IF NEEDED)
# =========================
# INPUT_DIR = r"C:\Users\DELL\Downloads\CRAFT-pytorch-master (2)\CRAFT-pytorch-master\sample"     # input images (.jpg)
# ===== CLI INPUT =====
if len(sys.argv) > 1:
    INPUT_DIR = sys.argv[1]
else:
    raise ValueError("❌ INPUT_DIR not provided")

CROP_OUTPUT_DIR = os.path.join(INPUT_DIR, "cropped_boxes")
CRAFT_MODEL_PATH = os.path.join(BASE_DIR, "craft_mlt_25k.pth")
RESULT_DIR = os.path.join(BASE_DIR, "sample_result")

# =========================
# AUTO DOWNLOAD CRAFT MODEL
# =========================
import urllib.request
import requests
if not os.path.exists(CRAFT_MODEL_PATH):
    print("⬇ Downloading CRAFT model...")
    url = "https://github.com/clovaai/CRAFT-pytorch/releases/download/v0.1/craft_mlt_25k.pth"
    r = requests.get(url)
    with open(CRAFT_MODEL_PATH, "wb") as f:
        f.write(r.content)
    print("✅ CRAFT model downloaded")

# =========================
# CRAFT PARAMETERS (TUNED)
# =========================
TEXT_THRESHOLD = 0.55
LOW_TEXT = 0.25
LINK_THRESHOLD = 0.4
CANVAS_SIZE = 1600
MAG_RATIO = 1.8
USE_CUDA = torch.cuda.is_available()
POLY = False


def copyStateDict(state_dict):
    new_state_dict = OrderedDict()
    for k, v in state_dict.items():
        name = k.replace("module.", "") if k.startswith("module") else k
        new_state_dict[name] = v
    return new_state_dict


def test_net(net, image):
    img_resized, target_ratio, _ = imgproc.resize_aspect_ratio(
        image,
        CANVAS_SIZE,
        interpolation=cv2.INTER_LINEAR,
        mag_ratio=MAG_RATIO
    )

    ratio_h = ratio_w = 1 / target_ratio

    x = imgproc.normalizeMeanVariance(img_resized)
    x = torch.from_numpy(x).permute(2, 0, 1)
    x = Variable(x.unsqueeze(0))

    if USE_CUDA:
        x = x.cuda()

    with torch.no_grad():
        y, _ = net(x)

    score_text = y[0, :, :, 0].cpu().numpy()
    score_link = y[0, :, :, 1].cpu().numpy()

    boxes, _ = craft_utils.getDetBoxes(
        score_text,
        score_link,
        TEXT_THRESHOLD,
        LINK_THRESHOLD,
        LOW_TEXT,
        POLY
    )

    boxes = craft_utils.adjustResultCoordinates(boxes, ratio_w, ratio_h)
    return boxes


# -------------------------
# Reading-order sorting
# -------------------------
def sort_boxes_reading_order(boxes, vertical_thresh=30):
    annotated = []
    for box in boxes:
        x, y, w, h = cv2.boundingRect(box)
        annotated.append((x, y, box))

    annotated.sort(key=lambda b: b[1])  # top → bottom

    rows = []
    current_row = []

    for item in annotated:
        if not current_row:
            current_row.append(item)
        else:
            _, y0, _ = current_row[0]
            _, y1, _ = item
            if abs(y1 - y0) <= vertical_thresh:
                current_row.append(item)
            else:
                rows.append(current_row)
                current_row = [item]

    if current_row:
        rows.append(current_row)

    sorted_boxes = []
    for row in rows:
        row.sort(key=lambda b: b[0])  # left → right
        sorted_boxes.extend(row)

    return [b[2] for b in sorted_boxes]


# =========================
# MAIN
# =========================
# if __name__ == "__main__":
#     os.makedirs(CROP_OUTPUT_DIR, exist_ok=True)
#     os.makedirs(RESULT_DIR, exist_ok=True)

#     device = torch.device("cuda" if USE_CUDA and torch.cuda.is_available() else "cpu")

#     # Load CRAFT
#     net = CRAFT()
#     net.load_state_dict(
#         copyStateDict(torch.load(CRAFT_MODEL_PATH, map_location=device))
#     )

#     if USE_CUDA:
#         net = net.cuda()
#         net = torch.nn.DataParallel(net)
#         cudnn.benchmark = False
#     else:
#         net = net.cpu()

#     net.eval()
#     print("✅ CRAFT model loaded")

#     image_list, _, _ = file_utils.get_files(INPUT_DIR)
#     image_list = [
#         os.path.join(INPUT_DIR, f)
#         for f in os.listdir(INPUT_DIR)
#         if f.lower().endswith((".jpg", ".png", ".jpeg"))
#     ]

#     for idx_img, image_path in enumerate(image_list, start=1):
#         print(f"[{idx_img}/{len(image_list)}] Processing {image_path}")

#         image = imgproc.loadImage(image_path)
#         image_bgr = cv2.imread(image_path)
#         orig_image = image_bgr.copy()
#         filename = os.path.splitext(os.path.basename(image_path))[0]

#         boxes = test_net(net, image)
#         boxes = sort_boxes_reading_order(boxes)

#         mapping = {"image": os.path.basename(image_path), "crops": []}

#         for idx, box in enumerate(boxes, start=1):
#             box = box.astype(np.int32)
#             x, y, w, h = cv2.boundingRect(box)

#             # skip noise
#             if w < 20 or h < 20:
#                 continue

#             x1 = max(x, 0)
#             y1 = max(y, 0)
#             x2 = min(x + w, orig_image.shape[1])
#             y2 = min(y + h, orig_image.shape[0])

#             crop = orig_image[y1:y2, x1:x2]
#             crop_name = f"{filename}_box{idx:03}.jpg"
#             crop_path = os.path.join(CROP_OUTPUT_DIR, crop_name)
#             cv2.imwrite(crop_path, crop)

#             mapping["crops"].append({
#                 "file": crop_name,
#                 "box": box.tolist(),
#                 "index": idx
#             })

#             # draw box + index for visualization
#             cv2.polylines(image_bgr, [box.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
#             cv2.putText(
#                 image_bgr, str(idx),
#                 (x, y - 10),
#                 cv2.FONT_HERSHEY_SIMPLEX,
#                 0.8, (0, 0, 255), 2
#             )

#         # Save visualization
#         result_path = os.path.join(RESULT_DIR, f"{filename}_result.jpg")
#         cv2.imwrite(result_path, image_bgr)

#         # Save mapping
#         with open(os.path.join(CROP_OUTPUT_DIR, f"{filename}_mapping.json"), "w") as jf:
#             json.dump(mapping, jf, indent=4)

# if __name__ == "__main__":

#     # 1. Run CRAFT (current logic already runs)
#     print("\n🚀 Step 1: CRAFT detection completed")

#     # 2. Run OCR on cropped boxes
#     cropped_boxes_dir = CROP_OUTPUT_DIR
#     print("\n🔠 Step 2: Running OCR...")
#     subprocess.run([
#         sys.executable,
#         "Recognition.py",
#         cropped_boxes_dir
#     ], check=True)

#     # 3. Run restitch + Excel
#     print("\n🧵 Step 3: Restitching + Excel...")
#     subprocess.run([
#         sys.executable,
#         "apo_restich.py"
#     ], check=True)

#     print("\n🎉 FULL PIPELINE COMPLETED SUCCESSFULLY")


def main():

    os.makedirs(CROP_OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    device = torch.device("cuda" if USE_CUDA and torch.cuda.is_available() else "cpu")

    net = CRAFT()
    net.load_state_dict(
        copyStateDict(torch.load(CRAFT_MODEL_PATH, map_location=device))
    )

    if USE_CUDA:
        net = torch.nn.DataParallel(net).cuda()
    net.eval()

    print("✅ CRAFT loaded")

    image_list = [
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]
    if not image_list:
        raise RuntimeError(f"No images found in {INPUT_DIR}")

    for idx_img, image_path in enumerate(image_list, start=1):
        print(f"[{idx_img}/{len(image_list)}] Processing {image_path}")

        image = imgproc.loadImage(image_path)
        image_bgr = cv2.imread(image_path)
        orig_image = image_bgr.copy()
        filename = os.path.splitext(os.path.basename(image_path))[0]

        boxes = test_net(net, image)
        boxes = sort_boxes_reading_order(boxes)

        mapping = {"image": os.path.basename(image_path), "crops": []}

        for idx, box in enumerate(boxes, start=1):
            box = box.astype(np.int32)
            x, y, w, h = cv2.boundingRect(box)

            if w < 20 or h < 20:
                continue

            x1 = max(x, 0)
            y1 = max(y, 0)
            x2 = min(x + w, orig_image.shape[1])
            y2 = min(y + h, orig_image.shape[0])

            crop = orig_image[y1:y2, x1:x2]
            crop_name = f"{filename}_box{idx:03}.jpg"
            crop_path = os.path.join(CROP_OUTPUT_DIR, crop_name)
            cv2.imwrite(crop_path, crop)

            mapping["crops"].append({
                "file": crop_name,
                "box": box.tolist(),
                "index": idx
            })

            cv2.polylines(image_bgr, [box.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
            cv2.putText(
                image_bgr, str(idx),
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 255), 2
            )

        cv2.imwrite(
            os.path.join(RESULT_DIR, f"{filename}_result.jpg"),
            image_bgr
        )

        with open(
            os.path.join(CROP_OUTPUT_DIR, f"{filename}_mapping.json"),
            "w"
        ) as jf:
            json.dump(mapping, jf, indent=4)


    print("🚀 Step 1: CRAFT done")

    subprocess.run([
        sys.executable,
        os.path.join(BASE_DIR, "st_Recognition.py"),
        CROP_OUTPUT_DIR
    ], check=True)

    print("🔠 OCR done")

    subprocess.run([
        sys.executable,
        os.path.join(BASE_DIR, "st_apo_restich.py"),
        INPUT_DIR
    ], check=True)

    print("🎉 FULL PIPELINE DONE")


if __name__ == "__main__":
    main()