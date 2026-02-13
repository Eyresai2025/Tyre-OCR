import os
import sys
import shutil
import subprocess
import base64
import streamlit as st
import streamlit.components.v1 as components
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageOps, ImageDraw
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
    except Exception:
        try:
            user_agent = st.context.headers.get("User-Agent", "").lower()
        except Exception:
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
# iOS Safari FIX (kept; helps other touch components)
# =====================================================
if IS_MOBILE:
    components.html(
        """
<script>
const apply = () => {
  try {
    const frames = window.parent.document.querySelectorAll("iframe");
    for (const f of frames) {
      const t = (f.getAttribute("title") || "").toLowerCase();
      if (t.includes("streamlit_drawable_canvas") || t.includes("st_canvas")) {
        f.style.touchAction = "none";
        f.style.overscrollBehavior = "contain";
        f.style.webkitUserSelect = "none";
      }
    }
  } catch (e) {}
};
setTimeout(apply, 500);
setTimeout(apply, 1500);
setTimeout(apply, 3000);
</script>
        """,
        height=0,
    )

# =====================================================
# MOBILE UI ENHANCEMENT (page-level) + scanner overlay styles
# =====================================================
if IS_MOBILE:
    st.markdown("""
<style>
/* Bigger touch targets */
.stButton button, .stDownloadButton button {
    min-height: 54px !important;
    font-size: 17px !important;
    border-radius: 12px !important;
}
.stRadio [role="radiogroup"] {
    flex-direction: row !important;
    justify-content: space-around !important;
}
.block-container {
    padding-left: 0.9rem !important;
    padding-right: 0.9rem !important;
}

/* Scanner frame */
.scanwrap {position: relative; width: 100%; max-width: 720px; margin: 0.2rem auto 0 auto;}
.scanwrap img {width: 100%; display: block; border-radius: 16px;}
.scan-overlay {
  position: absolute; inset: 0;
  border-radius: 16px;
  pointer-events: none;
}
.scan-dim {
  position:absolute; left:0; right:0; top:0; bottom:0;
  background: rgba(0,0,0,0.35);
  border-radius: 16px;
}
.scan-strip {
  position:absolute; left:8%; right:8%;
  border: 2px solid rgba(0,0,0,0.85);
  background: rgba(255,255,255,0.10);
  border-radius: 14px;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.08) inset;
}
.scan-line {
  position:absolute; left:10%; right:10%;
  height:2px;
  background: rgba(0,0,0,0.85);
  filter: blur(0.1px);
  animation: scanmove 1.6s ease-in-out infinite;
}
@keyframes scanmove {
  0%   { transform: translateY(-10px); opacity: 0.5; }
  50%  { transform: translateY(10px);  opacity: 1.0; }
  100% { transform: translateY(-10px); opacity: 0.5; }
}
.smallhint {font-size: 0.92rem; opacity: 0.9;}
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
        st.image(Image.open(logo_path), width="stretch")

    st.header("ROI / Scanner Settings")

    keep_exif = st.checkbox("Respect EXIF orientation", True)

    # Desktop ROI controls
    st.subheader("Desktop ROI")
    default_stroke = 10 if IS_MOBILE else 3
    stroke_width = st.slider("ROI border width", 1, 20, default_stroke)
    stroke_color = st.color_picker("ROI color", "#FF0000")

    st.subheader("Display")
    default_canvas = 520 if IS_MOBILE else 1200
    max_canvas_width = st.slider("Max canvas width (px)", 300, 2500, default_canvas)

    # Mobile scanner controls (only used for Mobile + Camera)
    st.subheader("Mobile Scanner Strip")
    strip_orientation = st.radio("Strip orientation", ["Horizontal", "Vertical"], horizontal=True)
    strip_thickness_pct = st.slider("Strip thickness (%)", 8, 60, 22)
    strip_pos_pct = st.slider("Strip position (%)", 0, 100, 50)

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
# MODE SWITCHING
# - Desktop/Laptop: ROI drawing unchanged (rect)
# - Mobile + Camera: strip mode (no ROI draw)
# - Mobile + Upload: fallback ROI (freedraw -> bbox) so upload still works
# =====================================================
MOBILE_STRIP_MODE = IS_MOBILE and (image_source == "Capture from Camera")

objects = []

def obj_to_bbox_pixels(obj):
    # Rect object
    if obj.get("type") != "path" or "path" not in obj:
        left = float(obj.get("left", 0))
        top = float(obj.get("top", 0))
        w = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
        h = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))
        return left, top, w, h

    # Freedraw path object
    xs, ys = [], []
    for seg in obj["path"]:
        nums = [v for v in seg[1:] if isinstance(v, (int, float))]
        for i in range(0, len(nums) - 1, 2):
            xs.append(nums[i])
            ys.append(nums[i + 1])

    if not xs or not ys:
        return 0, 0, 0, 0

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    left_rel = float(obj.get("left", 0)) + minx
    top_rel = float(obj.get("top", 0)) + miny
    w = maxx - minx
    h = maxy - miny
    return left_rel, top_rel, w, h

# =====================================================
# MOBILE STRIP PREVIEW (PRO UI)
# =====================================================
def render_scanner_overlay(preview_img: Image.Image, strip_style: str, show_line=True):
    buf = BytesIO()
    preview_img.save(buf, format="PNG")
    preview_b64 = base64.b64encode(buf.getvalue()).decode()

    line_div = '<div class="scan-line"></div>' if show_line else ''
    st.markdown(
        f"""
        <div class="scanwrap">
          <img src="data:image/png;base64,{preview_b64}">
          <div class="scan-overlay">
            <div class="scan-dim"></div>
            <div class="scan-strip" style="{strip_style}">
              {line_div}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =====================================================
# DRAW ROI OR STRIP MODE
# =====================================================
if MOBILE_STRIP_MODE:
    # Professional hint text
    st.markdown(
        "<div class='smallhint'>📱 Align the barcode/text inside the strip and capture. We will OCR only that strip (no ROI drawing).</div>",
        unsafe_allow_html=True
    )

    # preview sizing
    preview_max_w = 720
    prev_scale = min(1.0, preview_max_w / orig_w)
    prev_w = int(orig_w * prev_scale)
    prev_h = int(orig_h * prev_scale)
    preview = img.resize((prev_w, prev_h), Image.BILINEAR)

    thickness = int((strip_thickness_pct / 100.0) * (orig_h if strip_orientation == "Horizontal" else orig_w))
    thickness = max(12, thickness)
    pos = strip_pos_pct / 100.0

    if strip_orientation == "Horizontal":
        cy = int(pos * orig_h)
        y1 = max(0, cy - thickness // 2)
        y2 = min(orig_h, cy + thickness // 2)
        x1, x2 = 0, orig_w

        # overlay style in preview space
        cy_p = int(pos * prev_h)
        t_p = max(10, int(thickness * prev_scale))
        top_p = max(0, cy_p - t_p // 2)
        height_p = min(prev_h - top_p, t_p)
        strip_style = f"top:{top_p}px; height:{height_p}px;"
    else:
        cx = int(pos * orig_w)
        x1 = max(0, cx - thickness // 2)
        x2 = min(orig_w, cx + thickness // 2)
        y1, y2 = 0, orig_h

        cx_p = int(pos * prev_w)
        t_p = max(10, int(thickness * prev_scale))
        left_p = max(0, cx_p - t_p // 2)
        width_p = min(prev_w - left_p, t_p)
        strip_style = f"left:{left_p}px; width:{width_p}px; top:8%; bottom:8%; right:auto;"

    render_scanner_overlay(preview, strip_style, show_line=True)

    st.caption(f"Strip crop: x[{x1}:{x2}] y[{y1}:{y2}]")

    # Create exactly one ROI object programmatically so your pipeline stays same
    # We store bbox in ORIGINAL pixels via conversion later
    objects = [{
        "type": "rect",
        "left": x1 * scale,   # convert to DISPLAY pixels for compatibility
        "top": y1 * scale,
        "width": (x2 - x1) * scale,
        "height": (y2 - y1) * scale,
        "scaleX": 1,
        "scaleY": 1
    }]
    st.write("1 scanner strip selected")

else:
    # Desktop ROI / Mobile Upload fallback ROI
    if IS_MOBILE:
        st.info("📱 Upload mode: draw freehand over ROI (converted to rectangle).")
        drawing_mode = "freedraw"
        display_toolbar = False
    else:
        drawing_mode = "rect"
        display_toolbar = True

    canvas = st_canvas(
        background_image=img_display,
        height=canvas_h,
        width=canvas_w,
        drawing_mode=drawing_mode,
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        fill_color="rgba(255,0,0,0.15)" if IS_MOBILE else "rgba(0,0,0,0)",
        update_streamlit=True,
        key="roi_canvas",
        display_toolbar=display_toolbar,
    )

    objects = canvas.json_data["objects"] if canvas.json_data else []
    st.write(f"{len(objects)} ROI(s) drawn")

# =====================================================
# RUN PIPELINE (UNCHANGED)
# =====================================================
btn_label = "Run CRAFT + OCR + Restitch"
if MOBILE_STRIP_MODE:
    btn_label = "Run CRAFT + OCR on Scanner Strip"

if st.button(btn_label):

    if not objects:
        st.warning("Select at least one ROI / strip")
        st.stop()

    if os.path.exists(ROI_DIR):
        shutil.rmtree(ROI_DIR)
    os.makedirs(ROI_DIR, exist_ok=True)
    st.info("Old ROI data cleared")

    for roi_id, obj in enumerate(objects, start=1):
        left_d, top_d, width_d, height_d = obj_to_bbox_pixels(obj)

        left = int(left_d / scale)
        top = int(top_d / scale)
        width = int(width_d / scale)
        height = int(height_d / scale)

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

    stitched_excel_path = os.path.join(ROI_DIR, "stitched", "stitched_output.xlsx")
    if os.path.exists(stitched_excel_path):
        df = pd.read_excel(stitched_excel_path)
        st.dataframe(df, width="stretch")
        with open(stitched_excel_path, "rb") as f:
            st.download_button("Download Excel", f, "stitched_output.xlsx")
