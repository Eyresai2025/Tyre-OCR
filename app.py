import warnings
warnings.filterwarnings("ignore")

import os
import sys
import shutil
import subprocess
import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageOps, ImageDraw
import numpy as np
from io import BytesIO
import pandas as pd
import streamlit.components.v1 as components
import base64
import json
import time

# =====================================================
# BASE PATH
# =====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(
    page_title="ROI → OCR Pipeline",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add mobile-optimized CSS
st.markdown("""
<style>
    /* Make buttons more touch-friendly */
    .stButton button {
        min-height: 44px;
        min-width: 44px;
        font-size: 16px !important;
        margin: 5px 0 !important;
    }
    
    /* Better mobile spacing */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 1rem;
        }
        
        h1 {
            font-size: 24px !important;
        }
        
        h2 {
            font-size: 20px !important;
        }
        
        h3 {
            font-size: 18px !important;
        }
    }
    
    /* ROI Display */
    .roi-preview {
        border: 2px dashed #ff4b4b;
        position: relative;
        margin-top: 10px;
    }
    
    .stAlert {
        background-color: #f0f2f6;
    }
    
    /* Mobile-friendly sliders */
    .stSlider {
        padding: 10px 0 !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎯 ROI → OCR Pipeline (CRAFT + OCR)")

# =====================================================
# ROI DIRECTORY
# =====================================================
ROI_DIR = "sample"
os.makedirs(ROI_DIR, exist_ok=True)

# Clean ROI directory on startup
for f in os.listdir(ROI_DIR):
    f_path = os.path.join(ROI_DIR, f)
    if os.path.isfile(f_path):
        try:
            os.remove(f_path)
        except:
            pass

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

    st.markdown("---")
    
    # ---------- ROI SETTINGS ----------
    st.header("⚙️ ROI Settings")
    stroke_width = st.slider("ROI border width", 1, 10, 3)
    stroke_color = st.color_picker("ROI color", "#FF0000")
    
    st.markdown("---")
    
    # ---------- MOBILE MODE TOGGLE ----------
    st.header("📱 Device Settings")
    is_mobile = st.checkbox("Enable Mobile Mode", 
                           value=True,
                           help="Enable this when using on phones/tablets")
    
    st.markdown("---")
    
    # ---------- DISPLAY SETTINGS ----------
    st.header("🎨 Display")
    max_canvas_width = st.slider("Max canvas width (px)", 600, 2500, 900)
    keep_exif = st.checkbox("Respect EXIF orientation", True)
    
    st.markdown("---")
    
    # ---------- CLEAR ALL DATA ----------
    if st.button("🗑️ Clear All Data", use_container_width=True):
        # Clear session state
        st.session_state.roi_objects = []
        st.session_state.canvas_key = 0
        st.session_state.button_counter = 0
        
        # Clear ROI directory
        for f in os.listdir(ROI_DIR):
            f_path = os.path.join(ROI_DIR, f)
            if os.path.isfile(f_path):
                try:
                    os.remove(f_path)
                except:
                    pass
        
        # Clear cropped_boxes and stitched directories
        for dir_name in ["cropped_boxes", "stitched"]:
            dir_path = os.path.join(ROI_DIR, dir_name)
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
        
        st.rerun()

# =====================================================
# HELPER FUNCTIONS
# =====================================================
def draw_rois_on_image(img, rois, color="#FF0000", width=3):
    """Draw ROIs on image for preview"""
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy)
    
    for i, roi in enumerate(rois):
        left = roi.get("left", 0)
        top = roi.get("top", 0)
        right = left + roi.get("width", 0)
        bottom = top + roi.get("height", 0)
        
        draw.rectangle([left, top, right, bottom], outline=color, width=width)
        
        # Draw label
        draw.text((left + 5, top - 20), f"ROI {i+1}", fill=color, font=None)
    
    return img_copy

# =====================================================
# IMAGE SOURCE (Upload or Camera)
# =====================================================
st.subheader("📤 Select Image Source")

# Initialize session state
if 'roi_objects' not in st.session_state:
    st.session_state.roi_objects = []
if 'canvas_key' not in st.session_state:
    st.session_state.canvas_key = 0
if 'button_counter' not in st.session_state:
    st.session_state.button_counter = 0
if 'last_processed_image' not in st.session_state:
    st.session_state.last_processed_image = None
if 'ocr_completed' not in st.session_state:
    st.session_state.ocr_completed = False

image_source = st.radio(
    "Choose input method:",
    ["📁 Upload Image", "📸 Capture from Camera"],
    horizontal=True
)

uploaded = None

if image_source == "📁 Upload Image":
    uploaded = st.file_uploader(
        "Upload image",
        type=["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"],
        help="Supported formats: PNG, JPG, JPEG, BMP, TIFF, WEBP"
    )
elif image_source == "📸 Capture from Camera":
    uploaded = st.camera_input("Take a picture", help="Click the button to take a photo")

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

    st.caption(f"📐 Original image size: **{orig_w} × {orig_h}px**")

    # =====================================================
    # SCALE IMAGE FOR DISPLAY
    # =====================================================
    MAX_CANVAS_WIDTH = max_canvas_width
    display_w = min(orig_w, MAX_CANVAS_WIDTH)
    scale = display_w / orig_w
    display_h = int(orig_h * scale)

    img_display = img.resize((display_w, display_h), Image.Resampling.LANCZOS)
    
    # Reset OCR completed flag when new image is uploaded
    st.session_state.ocr_completed = False

else:
    st.info("👆 Upload or capture an image to start")
    st.stop()

# =====================================================
# SIMPLE MOBILE ROI DRAWING - GUARANTEED TO WORK
# =====================================================
st.subheader("✏️ Draw ROIs")

if is_mobile:
    # Display the image
    st.image(img_display, caption="📷 Current Image", use_column_width=True)
    
    st.markdown("---")
    st.markdown("### 🎯 Quick ROI Presets")
    st.markdown("Tap a button to add pre-defined ROI:")
    
    # Simple grid of pre-defined ROI positions
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🟥 Top Left", key=f"tl_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": 10,
                "top": 10,
                "width": display_w // 3,
                "height": display_h // 3,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    with col2:
        if st.button("🟥 Top Right", key=f"tr_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": display_w - (display_w // 3) - 10,
                "top": 10,
                "width": display_w // 3,
                "height": display_h // 3,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    with col3:
        if st.button("🟥 Center", key=f"center_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": display_w // 2 - 100,
                "top": display_h // 2 - 100,
                "width": 200,
                "height": 200,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🟥 Bottom Left", key=f"bl_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": 10,
                "top": display_h - (display_h // 3) - 10,
                "width": display_w // 3,
                "height": display_h // 3,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    with col2:
        if st.button("🟥 Bottom Right", key=f"br_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": display_w - (display_w // 3) - 10,
                "top": display_h - (display_h // 3) - 10,
                "width": display_w // 3,
                "height": display_h // 3,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    with col3:
        if st.button("🟥 Full Image", key=f"full_{st.session_state.canvas_key}", use_container_width=True):
            new_roi = {
                "left": 0,
                "top": 0,
                "width": display_w,
                "height": display_h,
                "scaleX": 1,
                "scaleY": 1
            }
            st.session_state.roi_objects.append(new_roi)
            st.session_state.canvas_key += 1
            st.rerun()
    
    st.markdown("---")
    st.markdown("### 🎨 Custom ROI")
    st.markdown("Adjust sliders to create custom ROI:")
    
    # Simple sliders for custom ROI
    col1, col2 = st.columns(2)
    with col1:
        roi_x = st.slider("X Position", 0, display_w-50, 50, key=f"x_{st.session_state.canvas_key}")
        roi_w = st.slider("Width", 50, display_w-roi_x, 150, key=f"w_{st.session_state.canvas_key}")
    
    with col2:
        roi_y = st.slider("Y Position", 0, display_h-50, 50, key=f"y_{st.session_state.canvas_key}")
        roi_h = st.slider("Height", 50, display_h-roi_y, 150, key=f"h_{st.session_state.canvas_key}")
    
    if st.button("➕ Add Custom ROI", key=f"add_custom_{st.session_state.canvas_key}", use_container_width=True):
        new_roi = {
            "left": roi_x,
            "top": roi_y,
            "width": roi_w,
            "height": roi_h,
            "scaleX": 1,
            "scaleY": 1
        }
        st.session_state.roi_objects.append(new_roi)
        st.session_state.canvas_key += 1
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 📏 Manual Coordinate Entry")
    st.markdown("Enter exact coordinates:")
    
    # Manual coordinate entry
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        x1 = st.number_input("X1", 0, display_w, 0, key=f"cx1_{st.session_state.canvas_key}")
    with col2:
        y1 = st.number_input("Y1", 0, display_h, 0, key=f"cy1_{st.session_state.canvas_key}")
    with col3:
        x2 = st.number_input("X2", 0, display_w, display_w, key=f"cx2_{st.session_state.canvas_key}")
    with col4:
        y2 = st.number_input("Y2", 0, display_h, display_h, key=f"cy2_{st.session_state.canvas_key}")
    
    if st.button("➕ Add ROI from Coordinates", key=f"add_coord_{st.session_state.canvas_key}", use_container_width=True):
        new_roi = {
            "left": min(x1, x2),
            "top": min(y1, y2),
            "width": abs(x2 - x1),
            "height": abs(y2 - y1),
            "scaleX": 1,
            "scaleY": 1
        }
        st.session_state.roi_objects.append(new_roi)
        st.session_state.canvas_key += 1
        st.rerun()
    
    # Show current ROIs on image
    if st.session_state.roi_objects:
        st.markdown("---")
        st.markdown("### 🎯 Current ROIs")
        
        # Draw ROIs on image
        img_with_rois = draw_rois_on_image(img_display, st.session_state.roi_objects, stroke_color, stroke_width)
        st.image(img_with_rois, caption=f"📸 {len(st.session_state.roi_objects)} ROI(s) drawn", use_column_width=True)
    
    objects = st.session_state.roi_objects

else:
    # Use original canvas for desktop
    col1, col2 = st.columns([3, 1])
    with col2:
        reset_key = f"reset_canvas_{st.session_state.canvas_key}_{st.session_state.button_counter}"
        if st.button("🔄 Reset Canvas", key=reset_key, use_container_width=True):
            st.session_state.roi_objects = []
            st.session_state.canvas_key += 1
            st.session_state.button_counter += 1
            st.rerun()
    
    canvas = st_canvas(
        background_image=img_display,
        height=display_h,
        width=display_w,
        drawing_mode="rect",
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        fill_color="rgba(0,0,0,0)",
        update_streamlit=True,
        key=f"roi_canvas_{st.session_state.canvas_key}",
        display_toolbar=True,
    )
    
    # Safe JSON extraction
    objects = []
    if canvas.json_data and "objects" in canvas.json_data:
        objects = canvas.json_data["objects"]
        st.session_state.roi_objects = objects
    
    # Display ROI preview with drawn rectangles
    if st.session_state.roi_objects:
        preview_img = draw_rois_on_image(img_display, st.session_state.roi_objects, stroke_color, stroke_width)
        st.image(preview_img, caption="Preview with ROIs", use_column_width=True)

# Display ROI count and controls (for both mobile and desktop)
st.markdown("---")
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

with col1:
    roi_count = len(st.session_state.roi_objects)
    st.info(f"📦 **{roi_count} ROI(s) drawn**")
    
    # Debug display (collapsed by default)
    with st.expander("🔍 Debug: View ROI Data"):
        st.json(st.session_state.roi_objects)

with col2:
    clear_key = f"clear_all_{st.session_state.canvas_key}_{st.session_state.button_counter}"
    if st.button("🗑 Clear All", key=clear_key, use_container_width=True):
        st.session_state.roi_objects = []
        st.session_state.canvas_key += 1
        st.session_state.button_counter += 1
        st.rerun()

with col3:
    undo_key = f"undo_last_{st.session_state.canvas_key}_{st.session_state.button_counter}"
    if st.button("↩ Undo Last", key=undo_key, use_container_width=True) and st.session_state.roi_objects:
        st.session_state.roi_objects = st.session_state.roi_objects[:-1]
        st.session_state.canvas_key += 1
        st.session_state.button_counter += 1
        st.rerun()

with col4:
    refresh_key = f"refresh_{st.session_state.canvas_key}_{st.session_state.button_counter}"
    if st.button("🔄 Refresh", key=refresh_key, use_container_width=True):
        st.rerun()

st.markdown("---")

# =====================================================
# RUN PIPELINE
# =====================================================
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run_pipeline = st.button("🚀 RUN CRAFT + OCR + RESTITCH", use_container_width=True, type="primary")

if run_pipeline:
    if not st.session_state.roi_objects:
        st.warning("⚠️ Please draw at least one ROI first")
        st.stop()

    # -------------------------------------------------
    # CLEAN OLD FILES COMPLETELY
    # -------------------------------------------------
    with st.spinner("🧹 Cleaning old data..."):
        # Clear ROI directory
        for f in os.listdir(ROI_DIR):
            f_path = os.path.join(ROI_DIR, f)
            if os.path.isfile(f_path):
                try:
                    os.remove(f_path)
                except:
                    pass
        
        # Clear cropped_boxes directory
        cropped_dir = os.path.join(ROI_DIR, "cropped_boxes")
        if os.path.exists(cropped_dir):
            shutil.rmtree(cropped_dir)
        
        # Clear stitched directory
        stitched_dir = os.path.join(ROI_DIR, "stitched")
        if os.path.exists(stitched_dir):
            shutil.rmtree(stitched_dir)
        
        # Recreate directories
        os.makedirs(cropped_dir, exist_ok=True)
        os.makedirs(stitched_dir, exist_ok=True)

    st.success("✅ Old data cleared")

    # -------------------------------------------------
    # SAVE ROIs
    # -------------------------------------------------
    with st.spinner("💾 Saving ROI images..."):
        saved_count = 0
        for roi_id, obj in enumerate(st.session_state.roi_objects, start=1):
            try:
                left = int(obj["left"] / scale)
                top = int(obj["top"] / scale)
                width = int(obj.get("width", 0) * obj.get("scaleX", 1) / scale)
                height = int(obj.get("height", 0) * obj.get("scaleY", 1) / scale)

                x1 = max(0, left)
                y1 = max(0, top)
                x2 = min(orig_w, x1 + width)
                y2 = min(orig_h, y1 + height)

                if x2 > x1 and y2 > y1:
                    roi = img_np[y1:y2, x1:x2]
                    roi_path = os.path.join(ROI_DIR, f"roi_{roi_id:02d}.jpg")
                    Image.fromarray(roi).save(roi_path, quality=95)
                    saved_count += 1
            except Exception as e:
                st.warning(f"Failed to save ROI {roi_id}: {e}")
                continue

    if saved_count == 0:
        st.error("❌ No valid ROIs to process")
        st.stop()
    
    st.success(f"✅ {saved_count} ROI images saved")

    # -------------------------------------------------
    # RUN CRAFT PIPELINE
    # -------------------------------------------------
    with st.spinner("🔄 Running CRAFT text detection..."):
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(BASE_DIR, "st_sample.py"), ROI_DIR],
                check=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            st.success("✅ CRAFT detection completed")
            
            if result.stdout:
                with st.expander("📋 View CRAFT output"):
                    st.code(result.stdout[-1000:])

        except subprocess.TimeoutExpired:
            st.error("❌ Pipeline timeout after 5 minutes")
            st.stop()
        except subprocess.CalledProcessError as e:
            st.error("❌ CRAFT pipeline failed")
            with st.expander("View error details"):
                st.code(e.stdout if e.stdout else e.stderr)
            st.stop()
        except FileNotFoundError:
            st.error(f"❌ Could not find st_sample.py")
            st.stop()

    # -------------------------------------------------
    # SHOW OCR OUTPUTS
    # -------------------------------------------------
    output_dir = os.path.join(ROI_DIR, "cropped_boxes", "output")
    
    # Wait for OCR to complete and files to be written
    time.sleep(2)

    if os.path.exists(output_dir):
        st.subheader("📄 OCR Results")
        
        # Display images in a grid
        output_images = sorted([f for f in os.listdir(output_dir) if f.lower().endswith((".jpg", ".png"))])
        
        if output_images:
            cols = st.columns(3)
            for idx, f in enumerate(output_images[:9]):
                with cols[idx % 3]:
                    st.image(
                        os.path.join(output_dir, f),
                        caption=f,
                        use_column_width=True
                    )
            if len(output_images) > 9:
                st.info(f"... and {len(output_images) - 9} more images")
        else:
            st.warning("⚠️ No OCR output images found")
    else:
        st.warning("⚠️ OCR output directory not found")

    # -------------------------------------------------
    # SHOW STITCHED EXCEL OUTPUT
    # -------------------------------------------------
    stitched_excel_path = os.path.join(ROI_DIR, "stitched", "stitched_output.xlsx")

    if os.path.exists(stitched_excel_path):
        st.subheader("📊 Stitched Excel Output")

        try:
            df = pd.read_excel(stitched_excel_path)
            st.dataframe(df, use_container_width=True)

            # Download button
            with open(stitched_excel_path, "rb") as f:
                st.download_button(
                    label="⬇ Download Excel File",
                    data=f,
                    file_name="stitched_output.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            st.session_state.ocr_completed = True
            
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
    else:
        st.warning("⚠️ Excel file not found")

# Add instructions for mobile users
if is_mobile:
    with st.expander("📱 Mobile Instructions", expanded=True):
        st.markdown("""
        ### ✅ How to add ROIs on mobile:
        
        1. **Quick ROI** - Tap any preset button (Top Left, Center, etc.)
        2. **Custom ROI** - Use sliders to adjust size and position
        3. **Manual ROI** - Enter exact coordinates
        4. **Clear All** - Remove all ROIs
        5. **Undo Last** - Remove the last ROI
        
        ### 📝 Notes:
        - ROI count updates **IMMEDIATELY** when you tap a button
        - Preview image shows all drawn ROIs
        - Click **Run Pipeline** when ready
        """)