# import os
# import glob
# import sys
# from paddleocr import TextRecognition

# # === Initialize OCR model ===
# def main():
#     model = TextRecognition()

#     # rest of your code stays SAME


# # === Accept input folder from CLI argument ===
#     if len(sys.argv) > 1:
#         input_folder = sys.argv[1]
#     else:
#         raise ValueError("❌ cropped_boxes path not provided")


#     output_folder = os.path.join(input_folder, "output")
#     os.makedirs(output_folder, exist_ok=True)

#     # === Read all image files ===
#     image_paths = glob.glob(os.path.join(input_folder, "*.jpg")) + \
#               glob.glob(os.path.join(input_folder, "*.png")) + \
#               glob.glob(os.path.join(input_folder, "*.jpeg"))

#     # === Loop over images ===
#     for image_path in image_paths:
#         if not image_path.lower().endswith((".jpg", ".jpeg", ".png")):
#             continue  # Skip non-image files

#         file_name = os.path.splitext(os.path.basename(image_path))[0]
#         print(f"🔍 Running OCR on: {file_name}")

#         # Run PaddleOCR Text Recognition
#         results = model.predict(input=image_path)

#         for idx, res in enumerate(results):
#             # === Save visualization image ===
#             vis_path = os.path.join(output_folder, f"{file_name}_ocr.jpg")
#             res.save_to_img(save_path=vis_path)

#             # === Save recognized text to JSON ===
#             json_path = os.path.join(output_folder, f"{file_name}_ocr.json")
#             res.save_to_json(save_path=json_path)

#             print(f"✅ Saved to: {vis_path}, {json_path}")

# if __name__ == "__main__":
#     main()

import os
import glob
import sys
import json
import cv2
from paddleocr import PaddleOCR
import numpy as np


def main(input_folder=None):
    # -------------------------------------------------
    # Resolve input folder
    # -------------------------------------------------
    if input_folder is None:
        if len(sys.argv) > 1:
            input_folder = sys.argv[1]
        else:
            raise ValueError("❌ cropped_boxes path not provided")

    if not os.path.isdir(input_folder):
        raise RuntimeError(f"❌ Invalid input folder: {input_folder}")

    # -------------------------------------------------
    # Initialize PaddleOCR (CLASSIC & STABLE)
    # -------------------------------------------------
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        use_gpu=False   # IMPORTANT: CPU only
    )

    # -------------------------------------------------
    # Output directory
    # -------------------------------------------------
    output_folder = os.path.join(input_folder, "output")
    os.makedirs(output_folder, exist_ok=True)

    # -------------------------------------------------
    # Read cropped images
    # -------------------------------------------------
    image_paths = []
    for ext in ("*.jpg", "*.png", "*.jpeg"):
        image_paths.extend(
            glob.glob(os.path.join(input_folder, ext))   # 🔥 NO recursive
        )

    # 🔥 VERY IMPORTANT: Remove already OCR-processed images
    image_paths = [
        p for p in image_paths
        if "_ocr" not in os.path.basename(p)
    ]


    if not image_paths:
        print(f"⚠️ No crop images found in {input_folder}, skipping OCR")
        return


    # -------------------------------------------------
    # OCR loop
    # -------------------------------------------------
    for image_path in image_paths:
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        print(f"🔍 Running OCR on: {file_name}")

        img = cv2.imread(image_path)
        if img is None:
            print(f"⚠️ Failed to read image: {image_path}")
            continue

        results = ocr.ocr(img, cls=True)

        # ---- prepare outputs ----
        vis_path = os.path.join(output_folder, f"{file_name}_ocr.jpg")
        json_path = os.path.join(output_folder, f"{file_name}_ocr.json")

        ocr_json = []
        vis_img = img.copy()

        # -------------------------------------------------
        # Parse OCR results
        # -------------------------------------------------
        if results is None:
            print("⚠️ No OCR result returned")
            continue

        for line in results:
            if line is None:
                print("⚠️ No text detected in this crop")
                continue

            for box, (text, score) in line:
                ocr_json.append({
                    "text": text,
                    "confidence": float(score),
                    "box": box
                })

                pts = [(int(x), int(y)) for x, y in box]
                cv2.polylines(
                    vis_img,
                    [cv2.convexHull(
                        np.array(pts)
                    )],
                    True,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    vis_img,
                    text,
                    pts[0],
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    1,
                    cv2.LINE_AA
                )


        # -------------------------------------------------
        # Save outputs
        # -------------------------------------------------
        cv2.imwrite(vis_path, vis_img)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ocr_json, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved OCR image: {vis_path}")
        print(f"✅ Saved OCR JSON : {json_path}")


if __name__ == "__main__":
    main()
