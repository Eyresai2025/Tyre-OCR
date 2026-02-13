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
# MOBILE DETECTION
# =====================================================
def is_mobile():
    try:
        from streamlit.web.server.websocket_headers import _get_headers
        headers = _get_headers()
        user_agent = headers.get("User-Agent", "").lower()
    except:
        try:
            user_agent = st.context.headers.get("User-Agent", "").lower()
        except:
            return False

    mobile_keywords = ["android", "iphone", "ipad", "ipod", "mobile", "tablet"]
    return any(k in user_agent for k in mobile_keywords)

IS_MOBILE = is_mobile()

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(
    page_title="ROI → OCR Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed" if IS_MOBILE else "expanded"
)

st.title("ROI → OCR (CRAFT + OCR)")

# =====================================================
# MOBILE UI ENHANCEMENT
# =====================================================
if IS_MOBILE:
    st.markdown("""
    <style>
    canvas {
        touch-action: none !important;
        -webkit-tap-highlight-color: transparent;
    }

    .stButton button, .stDownloadButton button {
        min-height: 55px !important;
        font-size: 18px !important;
        border-radius: 10px !important;
    }

    .stRadio [role="radiogroup"] {
        flex-direction: row !important;
        justify-content: space-around !important;
    }

    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

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
        st.image(Image.open(logo_path), use_column_width=True)

    st.header("ROI Settings")

    default_stroke = 8 if IS_MOBILE else 3
    stroke_width = st.slider("ROI border width", 1, 15, default_stroke)
    stroke_color = st.color_picker("ROI color", "#FF0000")

    st.header("Display")

    default_canvas = 500 if IS_MOBILE else 1200
    max_canvas_width = st.slider("Max canvas width (px)", 300, 2500, default_canvas)

    keep_exif = st.checkbox("Respect EXIF orientation", True)

# =====================================================
# IMAGE SOURCE
# =====================================================
st.subheader("Select Image Source")

image_source = st.radio(
    "Choose input method:",
    ["Upload Image", "Capture from Camera"],
    horizontal=True
)

uploaded = None

if image_source == "Upload Image":
    uploaded = st.file_uploader(
        "Upload image",
        type=["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"]
    )
else:
    uploaded = st.camera_input("Take a picture")

# =====================================================
# LOAD IMAGE
# =====================================================
if uploaded is not None:
    img = Image.open(uploaded)

    if keep_exif:
        img = ImageOps.exif_transpose(img)

    img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    img = Image.open(buf).convert("RGB")

    orig_w, orig_h = img.size
    img_np = np.array(img)

    st.caption(f"Original image size: {orig_w} × {orig_h}px")

    canvas_w = min(orig_w, max_canvas_width)
    scale = canvas_w / orig_w
    canvas_h = int(orig_h * scale)

    img_display = img.resize((canvas_w, canvas_h), Image.BILINEAR)

else:
    st.info("Upload or capture an image to start")
    st.stop()

# =====================================================
# DRAW ROI
# =====================================================
if IS_MOBILE:
    st.info("👉 Use finger or Apple Pencil to draw rectangle")

canvas = st_canvas(
    background_image=img_display,
    height=canvas_h,
    width=canvas_w,
    drawing_mode="rect",
    stroke_width=stroke_width,
    stroke_color=stroke_color,
    fill_color="rgba(255,0,0,0.2)" if IS_MOBILE else "rgba(0,0,0,0)",
    update_streamlit=True,
    key="roi_canvas",
    display_toolbar=True,
)

objects = canvas.json_data["objects"] if canvas.json_data else []

st.write(f"{len(objects)} ROI(s) drawn")

# =====================================================
# RUN PIPELINE (UNCHANGED)
# =====================================================
if st.button("Run CRAFT + OCR + Restitch"):

    if not objects:
        st.warning("Draw at least one ROI")
        st.stop()

    if os.path.exists(ROI_DIR):
        shutil.rmtree(ROI_DIR)

    os.makedirs(ROI_DIR, exist_ok=True)


    st.info("Old ROI data cleared")

    for roi_id, obj in enumerate(objects, start=1):
        left = int(obj["left"] / scale)
        top = int(obj["top"] / scale)
        width = int(obj["width"] * obj.get("scaleX", 1) / scale)
        height = int(obj["height"] * obj.get("scaleY", 1) / scale)

        x1, y1 = max(0, left), max(0, top)
        x2, y2 = min(orig_w, x1 + width), min(orig_h, y1 + height)

        if x2 <= x1 or y2 <= y1:
            continue

        roi = img_np[y1:y2, x1:x2]
        Image.fromarray(roi).save(os.path.join(ROI_DIR, f"roi_{roi_id:02}.jpg"))

    st.success("ROI images saved")

    subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "st_sample.py"), ROI_DIR],
        check=True
    )

    st.success("Pipeline completed successfully")

    # Show Excel
    stitched_excel_path = os.path.join(ROI_DIR, "stitched", "stitched_output.xlsx")
    if os.path.exists(stitched_excel_path):
        df = pd.read_excel(stitched_excel_path)
        st.dataframe(df, use_container_width=True)
        with open(stitched_excel_path, "rb") as f:
            st.download_button("Download Excel", f, "stitched_output.xlsx")
