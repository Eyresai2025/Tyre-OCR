import warnings
warnings.filterwarnings("ignore")

import os
import sys
import shutil
import subprocess
import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageOps
import numpy as np
from io import BytesIO
import pandas as pd

# =====================================================
# BASE PATH
# =====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(
    page_title="ROI → OCR Pipeline",
    layout="wide"
)
st.title("ROI → OCR (CRAFT + OCR)")


# =====================================================
# ROI DIRECTORY
# =====================================================
ROI_DIR = "sample"
os.makedirs(ROI_DIR, exist_ok=True)


# =====================================================
# SIDEBAR
# =====================================================
with st.sidebar:

    logo_path = os.path.join(BASE_DIR, "media", "LOGO-02.png")

    if os.path.exists(logo_path):
        logo = Image.open(logo_path)
        st.image(logo, use_column_width=True)
    else:
        st.error(f"Logo not found at {logo_path}")






    # ---------- ROI SETTINGS ----------
    st.header("ROI Settings")
    stroke_width = st.slider("ROI border width", 1, 10, 3)
    stroke_color = st.color_picker("ROI color", "#FF0000")

    # ---------- DISPLAY SETTINGS ----------
    st.header("Display")
    max_canvas_width = st.slider("Max canvas width (px)", 600, 2500, 1200)
    keep_exif = st.checkbox("Respect EXIF orientation", True)


# =====================================================
# IMAGE SOURCE (Upload or Camera)
# =====================================================

st.subheader("Select Image Source")

image_source = st.radio(
    "Choose input method:",
    ["Upload Image", "Capture from Camera"]
)

uploaded = None

if image_source == "Upload Image":
    uploaded = st.file_uploader(
        "Upload image",
        type=["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"]
    )

elif image_source == "Capture from Camera":
    uploaded = st.camera_input("Take a picture")

# =====================================================
# LOAD IMAGE SAFELY
# =====================================================

if uploaded is not None:

    try:
        img = Image.open(uploaded)

        if keep_exif:
            img = ImageOps.exif_transpose(img)

        img = img.convert("RGB")

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        img = Image.open(buf).convert("RGB")

    except Exception as e:
        st.error(f"Failed to load image: {e}")
        st.stop()

    orig_w, orig_h = img.size
    img_np = np.array(img)

    st.caption(f"Original image size: **{orig_w} × {orig_h}px**")

    # =====================================================
    # SCALE IMAGE FOR CANVAS (MOVED INSIDE)
    # =====================================================
    MAX_CANVAS_WIDTH = 600
    canvas_w = min(orig_w, MAX_CANVAS_WIDTH)

    scale = canvas_w / orig_w
    canvas_h = int(orig_h * scale)

    img_display = img.resize((canvas_w, canvas_h), Image.BILINEAR)

else:
    st.info("👆 Upload or capture an image to start")
    st.stop()



# =====================================================
# DRAW ROI CANVAS
# =====================================================
canvas = st_canvas(
    background_image=img_display,
    height=canvas_h,
    width=canvas_w,
    drawing_mode="rect",
    stroke_width=stroke_width,
    stroke_color=stroke_color,
    fill_color="rgba(0,0,0,0)",
    update_streamlit=True,
    key="roi_canvas",
    display_toolbar=False,

)

# Safe JSON extraction
objects = []
if canvas.json_data and "objects" in canvas.json_data:
    objects = canvas.json_data["objects"]

st.write(f"**{len(objects)} ROI(s) drawn**")

# =====================================================
# RUN PIPELINE
# =====================================================
if st.button("Run CRAFT + OCR + Restitch"):

    if not objects:
        st.warning("Draw at least one ROI")
        st.stop()

    # -------------------------------------------------
    # CLEAN OLD FILES
    # -------------------------------------------------
    for f in os.listdir(ROI_DIR):
        if f.lower().endswith((".jpg", ".png", ".jpeg")):
            os.remove(os.path.join(ROI_DIR, f))

    st.info("Old ROI data cleared")

    # -------------------------------------------------
    # SAVE ROIs
    # -------------------------------------------------
    for roi_id, obj in enumerate(objects, start=1):

        left = int(obj["left"] / scale)
        top = int(obj["top"] / scale)
        width = int(obj["width"] * obj.get("scaleX", 1) / scale)
        height = int(obj["height"] * obj.get("scaleY", 1) / scale)

        x1 = max(0, left)
        y1 = max(0, top)
        x2 = min(orig_w, x1 + width)
        y2 = min(orig_h, y1 + height)

        if x2 <= x1 or y2 <= y1:
            continue

        roi = img_np[y1:y2, x1:x2]
        roi_path = os.path.join(ROI_DIR, f"roi_{roi_id:02}.jpg")
        Image.fromarray(roi).save(roi_path)

    st.success("ROI images saved")

    # -------------------------------------------------
    # RUN CRAFT PIPELINE
    # -------------------------------------------------
    cropped_dir = os.path.join(ROI_DIR, "cropped_boxes")
    if os.path.exists(cropped_dir):
        shutil.rmtree(cropped_dir)

    st.info("Running pipeline...")

    try:
        subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "st_sample.py"), ROI_DIR],
            check=True
        )
        st.success("Pipeline completed successfully 🎉")

    except subprocess.CalledProcessError as e:
        st.error("Pipeline failed")
        st.code(str(e))
        st.stop()

    # -------------------------------------------------
    # SHOW OCR OUTPUTS
    # -------------------------------------------------
    output_dir = os.path.join(ROI_DIR, "cropped_boxes", "output")

    if os.path.exists(output_dir):
        st.subheader("OCR Results")

        for f in sorted(os.listdir(output_dir)):
            if f.lower().endswith(".jpg"):
                st.image(
                    os.path.join(output_dir, f),
                    caption=f,
                    use_column_width=True
                )
    else:
        st.warning("No OCR output found")

    # -------------------------------------------------
    # SHOW STITCHED EXCEL OUTPUT
    # -------------------------------------------------
    stitched_excel_path = os.path.join(ROI_DIR, "stitched", "stitched_output.xlsx")

    if os.path.exists(stitched_excel_path):
        st.subheader("Stitched Excel Output")

        df = pd.read_excel(stitched_excel_path)
        st.dataframe(df, use_container_width=True)

        # Download button
        with open(stitched_excel_path, "rb") as f:
            st.download_button(
                label="⬇ Download Excel",
                data=f,
                file_name="stitched_output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.warning("Excel file not found")

