import os
import json
import torch
import torch.backends.cudnn as cudnn
import numpy as np
import cv2
from collections import OrderedDict
from torch.autograd import Variable
import sys
import subprocess
import time
import warnings
warnings.filterwarnings("ignore")

# Import CRAFT modules
try:
    import craft_utils
    import imgproc
    from craft import CRAFT
    import file_utils
except ImportError as e:
    print(f"Error importing CRAFT modules: {e}")
    print("Make sure craft.py, craft_utils.py, imgproc.py, file_utils.py are in the same directory")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================
# PATHS
# =========================
if len(sys.argv) > 1:
    INPUT_DIR = sys.argv[1]
else:
    raise ValueError("❌ INPUT_DIR not provided")

# Create output directories
CROP_OUTPUT_DIR = os.path.join(INPUT_DIR, "cropped_boxes")
os.makedirs(CROP_OUTPUT_DIR, exist_ok=True)

CRAFT_MODEL_PATH = os.path.join(BASE_DIR, "craft_mlt_25k.pth")
RESULT_DIR = os.path.join(INPUT_DIR, "cropped_boxes", "visualization")
os.makedirs(RESULT_DIR, exist_ok=True)

# =========================
# CRAFT PARAMETERS
# =========================
TEXT_THRESHOLD = 0.55
LOW_TEXT = 0.25
LINK_THRESHOLD = 0.4
CANVAS_SIZE = 1600
MAG_RATIO = 1.8
USE_CUDA = torch.cuda.is_available()
POLY = False


def copyStateDict(state_dict):
    """Remove 'module.' prefix from state dict keys"""
    new_state_dict = OrderedDict()
    for k, v in state_dict.items():
        name = k.replace("module.", "") if k.startswith("module") else k
        new_state_dict[name] = v
    return new_state_dict


def test_net(net, image):
    """Run CRAFT on image and get text boxes"""
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


def sort_boxes_reading_order(boxes, vertical_thresh=30):
    """Sort boxes in reading order (top to bottom, left to right)"""
    if len(boxes) == 0:
        return boxes
    
    annotated = []
    for box in boxes:
        x, y, w, h = cv2.boundingRect(box)
        annotated.append((x, y, box))

    # Sort by Y coordinate (top to bottom)
    annotated.sort(key=lambda b: b[1])

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
        row.sort(key=lambda b: b[0])  # Sort by X (left to right)
        sorted_boxes.extend(row)

    return [b[2] for b in sorted_boxes]


def main():
    """Main function to run CRAFT detection"""
    print(f"\n{'='*50}")
    print(f"🚀 CRAFT Text Detection Pipeline")
    print(f"{'='*50}")
    print(f"📁 Input directory: {INPUT_DIR}")
    print(f"📁 Output directory: {CROP_OUTPUT_DIR}")
    print(f"{'='*50}\n")

    # Check if model exists
    if not os.path.exists(CRAFT_MODEL_PATH):
        raise FileNotFoundError(f"❌ CRAFT model not found at {CRAFT_MODEL_PATH}")

    # Setup device
    device = torch.device("cuda" if USE_CUDA and torch.cuda.is_available() else "cpu")
    print(f"💻 Using device: {device}")

    # Load CRAFT model
    print("📦 Loading CRAFT model...")
    net = CRAFT()
    
    try:
        state_dict = torch.load(CRAFT_MODEL_PATH, map_location=device)
        net.load_state_dict(copyStateDict(state_dict))
        print("✅ CRAFT model loaded successfully")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        sys.exit(1)

    if USE_CUDA:
        net = torch.nn.DataParallel(net).cuda()
    net.eval()

    # Get list of images
    image_list = [
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]
    
    if not image_list:
        print(f"❌ No images found in {INPUT_DIR}")
        return

    print(f"📸 Found {len(image_list)} image(s) to process\n")

    total_boxes = 0
    
    for idx_img, image_path in enumerate(image_list, start=1):
        print(f"[{idx_img}/{len(image_list)}] Processing: {os.path.basename(image_path)}")
        
        try:
            # Load images
            image = imgproc.loadImage(image_path)
            image_bgr = cv2.imread(image_path)
            
            if image_bgr is None:
                print(f"  ⚠️  Failed to load image: {image_path}")
                continue
                
            orig_image = image_bgr.copy()
            filename = os.path.splitext(os.path.basename(image_path))[0]

            # Detect text boxes
            boxes = test_net(net, image)
            
            if len(boxes) == 0:
                print(f"  ⚠️  No text detected in {filename}")
                continue
                
            # Sort boxes in reading order
            boxes = sort_boxes_reading_order(boxes)
            print(f"  📦 Detected {len(boxes)} text regions")

            mapping = {
                "image": os.path.basename(image_path),
                "total_boxes": len(boxes),
                "crops": []
            }

            # Process each box
            for idx, box in enumerate(boxes, start=1):
                box = box.astype(np.int32)
                x, y, w, h = cv2.boundingRect(box)

                # Skip small boxes
                if w < 15 or h < 15:
                    continue

                x1 = max(x, 0)
                y1 = max(y, 0)
                x2 = min(x + w, orig_image.shape[1])
                y2 = min(y + h, orig_image.shape[0])

                # Crop and save
                crop = orig_image[y1:y2, x1:x2]
                crop_name = f"{filename}_box{idx:03d}.jpg"
                crop_path = os.path.join(CROP_OUTPUT_DIR, crop_name)
                cv2.imwrite(crop_path, crop)

                mapping["crops"].append({
                    "file": crop_name,
                    "box": box.tolist(),
                    "index": idx,
                    "bbox": [x1, y1, x2, y2]
                })

                # Draw visualization
                cv2.polylines(image_bgr, [box.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
                cv2.putText(
                    image_bgr, str(idx),
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 0, 255), 2
                )

            # Save visualization
            result_path = os.path.join(RESULT_DIR, f"{filename}_result.jpg")
            cv2.imwrite(result_path, image_bgr)
            print(f"  ✅ Saved visualization to {os.path.basename(result_path)}")

            # Save mapping
            mapping_path = os.path.join(CROP_OUTPUT_DIR, f"{filename}_mapping.json")
            with open(mapping_path, "w") as jf:
                json.dump(mapping, jf, indent=2)
            print(f"  ✅ Saved mapping to {os.path.basename(mapping_path)}")
            
            total_boxes += len(mapping["crops"])

        except Exception as e:
            print(f"  ❌ Error processing {image_path}: {e}")
            continue

    print(f"\n{'='*50}")
    print(f"✅ CRAFT detection completed!")
    print(f"📊 Total text regions detected: {total_boxes}")
    print(f"{'='*50}\n")

    # =============================================
    # STEP 2: Run OCR on cropped boxes
    # =============================================
    print("🔠 Step 2: Running OCR on cropped text regions...")
    
    ocr_script = os.path.join(BASE_DIR, "st_Recognition.py")
    if os.path.exists(ocr_script):
        try:
            subprocess.run([
                sys.executable,
                ocr_script,
                CROP_OUTPUT_DIR
            ], check=True)
            print("✅ OCR completed successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ OCR failed with error code {e.returncode}")
            sys.exit(1)
    else:
        print(f"⚠️  OCR script not found at {ocr_script}")
        print("   Please ensure st_Recognition.py exists")

    # =============================================
    # STEP 3: Run restitching
    # =============================================
    print("\n🧵 Step 3: Restitching and generating Excel...")
    
    restitch_script = os.path.join(BASE_DIR, "st_apo_restich.py")
    if os.path.exists(restitch_script):
        try:
            subprocess.run([
                sys.executable,
                restitch_script,
                INPUT_DIR
            ], check=True)
            print("✅ Restitching completed successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ Restitching failed with error code {e.returncode}")
            sys.exit(1)
    else:
        print(f"⚠️  Restitch script not found at {restitch_script}")

    print(f"\n{'='*50}")
    print("🎉 FULL PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()