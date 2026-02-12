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
    /* Improve touch handling for canvas */
    canvas {
        touch-action: none !important;
        -webkit-tap-highlight-color: transparent;
    }
    
    /* Make buttons more touch-friendly */
    .stButton button {
        min-height: 44px;
        min-width: 44px;
        font-size: 16px !important;
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
    is_mobile = st.checkbox("Enable Mobile Mode (Touch Support)", 
                           value=False,
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
def get_image_data_url(img):
    """Convert PIL Image to data URL for HTML canvas"""
    try:
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        st.error(f"Error converting image: {e}")
        return ""

def draw_rois_on_image(img, rois, color="#FF0000", width=3):
    """Draw ROIs on image for preview"""
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy)
    
    for roi in rois:
        left = roi.get("left", 0)
        top = roi.get("top", 0)
        right = left + roi.get("width", 0)
        bottom = top + roi.get("height", 0)
        
        draw.rectangle([left, top, right, bottom], outline=color, width=width)
        
        # Draw label
        draw.text((left + 5, top - 15), f"ROI", fill=color)
    
    return img_copy

def create_mobile_canvas(img_display, canvas_w, canvas_h, stroke_width, stroke_color, component_key):
    """Create a mobile-optimized canvas with touch support - SIMPLIFIED & RELIABLE"""
    
    img_data_url = get_image_data_url(img_display)
    
    # Create a unique ID for this canvas instance
    canvas_id = f"mobile_canvas_{component_key}"
    
    canvas_html = f"""
    <div style="width: 100%; max-width: {canvas_w}px; margin: 0 auto; padding: 10px;">
        <div style="position: relative; width: {canvas_w}px; height: {canvas_h}px; border: 3px solid #ff4b4b; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <canvas id="{canvas_id}" width="{canvas_w}" height="{canvas_h}" 
                    style="display: block; width: 100%; height: 100%; touch-action: none; background-color: #f0f2f6;">
            </canvas>
            <div style="position: absolute; top: 10px; left: 10px; background-color: rgba(255,75,75,0.9); color: white; padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: bold; z-index: 1000;">
                👆 Drag to draw ROI
            </div>
        </div>
        
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button id="clearBtn_{component_key}" style="flex: 1; padding: 15px; background-color: #dc3545; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer;">🗑 Clear All</button>
            <button id="undoBtn_{component_key}" style="flex: 1; padding: 15px; background-color: #6c757d; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer;">↩ Undo Last</button>
        </div>
        
        <div id="roiDisplay_{component_key}" style="margin-top: 15px; padding: 15px; background-color: #e8f0fe; border-radius: 8px; text-align: center; font-size: 18px; font-weight: bold; color: #1f1f1f; border: 2px solid #ff4b4b;">
            📦 ROIs Drawn: <span id="roiCount_{component_key}" style="color: #ff4b4b; font-size: 28px;">0</span>
        </div>
    </div>
    
    <script>
    (function() {{
        const canvas = document.getElementById('{canvas_id}');
        const ctx = canvas.getContext('2d');
        const img = new Image();
        img.src = '{img_data_url}';
        
        // Store ROIs
        let rois = [];
        let isDrawing = false;
        let startX = 0, startY = 0;
        
        // Load image
        img.onload = function() {{
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            drawROIs();
            sendToStreamlit();
        }};
        
        // Draw all ROIs
        function drawROIs() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            rois.forEach((roi, index) => {{
                ctx.strokeStyle = '{stroke_color}';
                ctx.lineWidth = {stroke_width};
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
                
                // Draw label
                ctx.fillStyle = '{stroke_color}';
                ctx.font = 'bold 16px Arial';
                ctx.fillText(`${{index + 1}}`, roi.x + 10, roi.y + 30);
            }});
            
            document.getElementById('roiCount_{component_key}').innerText = rois.length;
        }}
        
        // Touch events
        canvas.addEventListener('touchstart', (e) => {{
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const x = (e.touches[0].clientX - rect.left) * (canvas.width / rect.width);
            const y = (e.touches[0].clientY - rect.top) * (canvas.height / rect.height);
            
            isDrawing = true;
            startX = x;
            startY = y;
        }}, {{ passive: false }});
        
        canvas.addEventListener('touchmove', (e) => {{
            e.preventDefault();
            if (!isDrawing) return;
            
            const rect = canvas.getBoundingClientRect();
            const x = (e.touches[0].clientX - rect.left) * (canvas.width / rect.width);
            const y = (e.touches[0].clientY - rect.top) * (canvas.height / rect.height);
            
            // Redraw
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            // Draw existing ROIs
            rois.forEach(roi => {{
                ctx.strokeStyle = '{stroke_color}';
                ctx.lineWidth = {stroke_width};
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
            }});
            
            // Draw current rectangle
            ctx.strokeStyle = '{stroke_color}';
            ctx.lineWidth = {stroke_width};
            ctx.strokeRect(startX, startY, x - startX, y - startY);
            
            // Show dimensions
            const width = Math.abs(x - startX);
            const height = Math.abs(y - startY);
            ctx.fillStyle = '#000';
            ctx.font = 'bold 14px Arial';
            ctx.fillText(`${{Math.round(width)}}x${{Math.round(height)}}`, x + 10, y + 10);
        }}, {{ passive: false }});
        
        canvas.addEventListener('touchend', (e) => {{
            e.preventDefault();
            if (!isDrawing) return;
            
            const rect = canvas.getBoundingClientRect();
            const x = (e.changedTouches[0].clientX - rect.left) * (canvas.width / rect.width);
            const y = (e.changedTouches[0].clientY - rect.top) * (canvas.height / rect.height);
            
            const width = x - startX;
            const height = y - startY;
            
            if (Math.abs(width) > 15 && Math.abs(height) > 15) {{
                const roi = {{
                    x: width > 0 ? startX : x,
                    y: height > 0 ? startY : y,
                    w: Math.abs(width),
                    h: Math.abs(height)
                }};
                
                rois.push(roi);
                drawROIs();
                sendToStreamlit();
            }}
            
            isDrawing = false;
        }}, {{ passive: false }});
        
        canvas.addEventListener('touchcancel', (e) => {{
            e.preventDefault();
            isDrawing = false;
        }}, {{ passive: false }});
        
        // Clear all ROIs
        document.getElementById('clearBtn_{component_key}').addEventListener('click', function(e) {{
            e.preventDefault();
            rois = [];
            drawROIs();
            sendToStreamlit();
        }});
        
        // Undo last ROI
        document.getElementById('undoBtn_{component_key}').addEventListener('click', function(e) {{
            e.preventDefault();
            rois.pop();
            drawROIs();
            sendToStreamlit();
        }});
        
        // Send ROI data to Streamlit
        function sendToStreamlit() {{
            const roiData = rois.map(roi => ({{
                left: Math.round(roi.x),
                top: Math.round(roi.y),
                width: Math.round(roi.w),
                height: Math.round(roi.h),
                scaleX: 1,
                scaleY: 1
            }}));
            
            // Store in sessionStorage
            sessionStorage.setItem('streamlit_rois', JSON.stringify(roiData));
            
            // Send to Streamlit
            const frame = window.parent;
            if (frame) {{
                frame.postMessage({{
                    type: 'streamlit:setComponentValue',
                    data: roiData
                }}, '*');
            }}
            
            console.log('ROIs sent:', roiData.length);
        }}
        
        // Check for existing ROIs
        const savedROIs = sessionStorage.getItem('streamlit_rois');
        if (savedROIs) {{
            try {{
                const parsed = JSON.parse(savedROIs);
                if (parsed && parsed.length > 0) {{
                    rois = parsed.map(r => ({{
                        x: r.left,
                        y: r.top,
                        w: r.width,
                        h: r.height
                    }}));
                    setTimeout(() => {{
                        drawROIs();
                    }}, 100);
                }}
            }} catch(e) {{}}
        }}
        
        // Send initial data
        setTimeout(sendToStreamlit, 500);
    }})();
    </script>
    """
    
    # Return the component value
    component_value = components.html(canvas_html, height=canvas_h + 200, width=canvas_w + 40)
    
    # Try to get ROI data from sessionStorage via JavaScript
    try:
        # Check if we have ROI data in session state from previous runs
        if 'temp_roi_data' in st.session_state:
            st.session_state.roi_objects = st.session_state.temp_roi_data
            st.session_state.temp_roi_data = None
    except Exception as e:
        pass
    
    return component_value

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
    # SCALE IMAGE FOR CANVAS
    # =====================================================
    MAX_CANVAS_WIDTH = max_canvas_width
    canvas_w = min(orig_w, MAX_CANVAS_WIDTH)
    scale = canvas_w / orig_w
    canvas_h = int(orig_h * scale)

    img_display = img.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)
    
    # Reset OCR completed flag when new image is uploaded
    st.session_state.ocr_completed = False

else:
    st.info("👆 Upload or capture an image to start")
    st.stop()

# =====================================================
# DRAW ROI CANVAS - WITH MOBILE SUPPORT
# =====================================================
st.subheader("✏️ Draw ROIs")

# Add reset button for canvas
col1, col2 = st.columns([3, 1])
with col2:
    reset_key = f"reset_canvas_{st.session_state.canvas_key}_{st.session_state.button_counter}"
    if st.button("🔄 Reset Canvas", key=reset_key, use_container_width=True):
        st.session_state.roi_objects = []
        st.session_state.canvas_key += 1
        st.session_state.button_counter += 1
        st.rerun()

if is_mobile:
    # Use mobile-optimized canvas
    canvas_result = create_mobile_canvas(
        img_display, 
        canvas_w, 
        canvas_h, 
        stroke_width, 
        stroke_color,
        st.session_state.canvas_key
    )
    
    # JavaScript to capture postMessage data
    components.html("""
    <script>
    window.addEventListener('message', function(e) {
        if (e.data.type === 'streamlit:setComponentValue') {
            // Store in sessionStorage
            sessionStorage.setItem('streamlit_rois', JSON.stringify(e.data.data));
            console.log('Received ROIs:', e.data.data.length);
        }
    });
    </script>
    """, height=0)
    
    # Try to get ROI data from sessionStorage
    try:
        roi_data = st.query_params.get("streamlit_rois")
        if roi_data:
            import json
            try:
                new_rois = json.loads(roi_data)
                if new_rois and len(new_rois) > 0:
                    st.session_state.roi_objects = new_rois
            except:
                pass
    except:
        pass
    
    # Add Load ROIs button
    col1, col2, col3 = st.columns(3)
    with col2:
        load_key = f"load_rois_{st.session_state.canvas_key}_{st.session_state.button_counter}"
        if st.button("🔄 Load ROIs from Canvas", key=load_key, use_container_width=True):
            st.rerun()
    
    # Use session state for objects
    objects = st.session_state.roi_objects
    
else:
    # Use original canvas for desktop
    canvas = st_canvas(
        background_image=img_display,
        height=canvas_h,
        width=canvas_w,
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

# Display ROI count and controls
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

# Manual ROI entry as fallback
if is_mobile:
    with st.expander("📝 Manual ROI Entry (Fallback)", expanded=False):
        st.markdown("If drawing doesn't work, enter coordinates manually:")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            x1_key = f"manual_x1_{st.session_state.canvas_key}_{st.session_state.button_counter}"
            x1 = st.number_input("X1", 0, canvas_w, 0, key=x1_key)
        with col2:
            y1_key = f"manual_y1_{st.session_state.canvas_key}_{st.session_state.button_counter}"
            y1 = st.number_input("Y1", 0, canvas_h, 0, key=y1_key)
        with col3:
            x2_key = f"manual_x2_{st.session_state.canvas_key}_{st.session_state.button_counter}"
            x2 = st.number_input("X2", 0, canvas_w, canvas_w, key=x2_key)
        with col4:
            y2_key = f"manual_y2_{st.session_state.canvas_key}_{st.session_state.button_counter}"
            y2 = st.number_input("Y2", 0, canvas_h, canvas_h, key=y2_key)
        
        add_key = f"add_manual_{st.session_state.canvas_key}_{st.session_state.button_counter}"
        if st.button("➕ Add Manual ROI", key=add_key, use_container_width=True):
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
            st.session_state.button_counter += 1
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
                    st.code(result.stdout[-1000:])  # Show last 1000 chars

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
            for idx, f in enumerate(output_images[:9]):  # Show first 9 images
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
    with st.expander("📱 Mobile Drawing Instructions"):
        st.markdown("""
        ### How to draw ROIs on mobile:
        
        1. **Tap and hold** on the canvas to start drawing
        2. **Drag** your finger to draw a rectangle
        3. **Release** to complete the ROI
        4. The ROI count will increase automatically
        5. Use **Clear All** to remove all ROIs
        6. Use **Undo Last** to remove the last ROI
        
        ### Troubleshooting:
        - If ROIs aren't saving, tap **Refresh** button
        - Check **Debug** section to see if ROI data is captured
        - Make sure ROI is at least 15x15 pixels
        - Use **Manual ROI Entry** as fallback if drawing doesn't work
        """)