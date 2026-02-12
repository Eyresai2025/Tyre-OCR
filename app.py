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
import streamlit.components.v1 as components
import base64

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
    
    /* Custom canvas styling */
    .canvas-container {
        margin: 0 auto;
        position: relative;
        border: 2px solid #f0f2f6;
        border-radius: 8px;
        overflow: hidden;
    }
    
    .roi-controls {
        display: flex;
        gap: 10px;
        margin-top: 10px;
        flex-wrap: wrap;
    }
    
    .roi-button {
        background-color: #ff4b4b;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        cursor: pointer;
        font-size: 14px;
        flex: 1;
        min-width: 120px;
    }
    
    .roi-button:hover {
        background-color: #ff3333;
    }
    
    .roi-count {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        font-weight: bold;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

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
    
    # ---------- MOBILE MODE TOGGLE ----------
    st.header("Device Settings")
    is_mobile = st.checkbox("📱 Mobile mode (Enable for touch devices)", 
                           value=False,
                           help="Enable this if drawing ROI doesn't work on your device")
    
    # ---------- DISPLAY SETTINGS ----------
    st.header("Display")
    max_canvas_width = st.slider("Max canvas width (px)", 600, 2500, 900)
    keep_exif = st.checkbox("Respect EXIF orientation", True)

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

def create_mobile_canvas(img_display, canvas_w, canvas_h, stroke_width, stroke_color):
    """Create a mobile-optimized canvas with touch support"""
    
    img_data_url = get_image_data_url(img_display)
    
    canvas_html = f"""
    <div style="width: 100%; max-width: {canvas_w}px; margin: 0 auto;">
        <div class="canvas-container" style="position: relative; width: {canvas_w}px; height: {canvas_h}px;">
            <canvas id="roiCanvas" width="{canvas_w}" height="{canvas_h}" 
                    style="display: block; width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;">
            </canvas>
        </div>
        
        <div class="roi-controls">
            <button id="clearBtn" class="roi-button" style="background-color: #dc3545;">🗑 Clear All</button>
            <button id="undoBtn" class="roi-button" style="background-color: #6c757d;">↩ Undo Last</button>
        </div>
        
        <div id="roiCount" class="roi-count">
            ROIs: <span id="roiCountValue">0</span>
        </div>
    </div>
    
    <script>
        // Initialize canvas
        const canvas = document.getElementById('roiCanvas');
        const ctx = canvas.getContext('2d');
        const img = new Image();
        img.src = '{img_data_url}';
        
        // State management
        let rois = [];
        let isDrawing = false;
        let startX, startY;
        let currentRect = null;
        
        // Load image and draw
        img.onload = function() {{
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }};
        
        // Handle image loading errors
        img.onerror = function() {{
            console.error('Failed to load image');
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#dc3545';
            ctx.font = '14px Arial';
            ctx.fillText('Failed to load image', 10, 50);
        }};
        
        // Touch events for mobile
        canvas.addEventListener('touchstart', handleStart, {{ passive: false }});
        canvas.addEventListener('touchmove', handleMove, {{ passive: false }});
        canvas.addEventListener('touchend', handleEnd, {{ passive: false }});
        canvas.addEventListener('touchcancel', handleEnd, {{ passive: false }});
        
        // Mouse events for desktop
        canvas.addEventListener('mousedown', handleStart);
        canvas.addEventListener('mousemove', handleMove);
        canvas.addEventListener('mouseup', handleEnd);
        canvas.addEventListener('mouseout', handleEnd);
        
        // Prevent default touch behaviors
        function preventDefault(e) {{
            e.preventDefault();
        }}
        
        canvas.addEventListener('touchstart', preventDefault, {{ passive: false }});
        canvas.addEventListener('touchmove', preventDefault, {{ passive: false }});
        
        // Get coordinates relative to canvas
        function getEventPosition(e) {{
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            
            let clientX, clientY;
            
            if (e.touches) {{
                // Touch event
                clientX = e.touches[0].clientX;
                clientY = e.touches[0].clientY;
            }} else {{
                // Mouse event
                clientX = e.clientX;
                clientY = e.clientY;
            }}
            
            let x = (clientX - rect.left) * scaleX;
            let y = (clientY - rect.top) * scaleY;
            
            // Constrain to canvas boundaries
            x = Math.max(0, Math.min(x, canvas.width));
            y = Math.max(0, Math.min(y, canvas.height));
            
            return {{ x, y }};
        }}
        
        // Start drawing
        function handleStart(e) {{
            e.preventDefault();
            e.stopPropagation();
            
            const pos = getEventPosition(e);
            isDrawing = true;
            startX = pos.x;
            startY = pos.y;
            currentRect = null;
        }}
        
        // Draw rectangle
        function handleMove(e) {{
            e.preventDefault();
            e.stopPropagation();
            
            if (!isDrawing) return;
            
            const pos = getEventPosition(e);
            
            // Clear canvas and redraw
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            // Draw existing ROIs
            rois.forEach(roi => {{
                ctx.strokeStyle = roi.color || '{stroke_color}';
                ctx.lineWidth = roi.width || {stroke_width};
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
                
                // Draw resize handle
                ctx.fillStyle = '#ffffff';
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 1;
                ctx.fillRect(roi.x + roi.w - 5, roi.y + roi.h - 5, 10, 10);
                ctx.strokeRect(roi.x + roi.w - 5, roi.y + roi.h - 5, 10, 10);
            }});
            
            // Draw current rectangle
            const width = pos.x - startX;
            const height = pos.y - startY;
            
            ctx.strokeStyle = '{stroke_color}';
            ctx.lineWidth = {stroke_width};
            ctx.strokeRect(startX, startY, width, height);
            
            // Show dimensions
            ctx.fillStyle = '#000000';
            ctx.font = '12px Arial';
            ctx.fillText(`${{Math.abs(Math.round(width))}}x${{Math.abs(Math.round(height))}}`, 
                        pos.x + 10, pos.y + 10);
        }}
        
        // Stop drawing and save ROI
        function handleEnd(e) {{
            e.preventDefault();
            e.stopPropagation();
            
            if (!isDrawing) return;
            
            const pos = getEventPosition(e);
            const width = pos.x - startX;
            const height = pos.y - startY;
            
            // Only save if rectangle is large enough
            if (Math.abs(width) > 10 && Math.abs(height) > 10) {{
                const roi = {{
                    id: Date.now() + Math.random(),
                    x: width > 0 ? startX : pos.x,
                    y: height > 0 ? startY : pos.y,
                    w: Math.abs(width),
                    h: Math.abs(height),
                    color: '{stroke_color}',
                    width: {stroke_width}
                }};
                
                rois.push(roi);
                updateROICount();
                sendROIData();
            }}
            
            // Redraw everything
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            rois.forEach(roi => {{
                ctx.strokeStyle = roi.color;
                ctx.lineWidth = roi.width;
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
            }});
            
            isDrawing = false;
        }}
        
        // Clear all ROIs
        function clearROIs() {{
            rois = [];
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            updateROICount();
            sendROIData();
        }}
        
        // Undo last ROI
        function undoLastROI() {{
            rois.pop();
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            rois.forEach(roi => {{
                ctx.strokeStyle = roi.color;
                ctx.lineWidth = roi.width;
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
            }});
            
            updateROICount();
            sendROIData();
        }}
        
        // Update ROI count display
        function updateROICount() {{
            document.getElementById('roiCountValue').innerText = rois.length;
        }}
        
        // Send ROI data to Streamlit
        function sendROIData() {{
            const roiData = rois.map((roi, index) => ({{
                left: roi.x,
                top: roi.y,
                width: roi.w,
                height: roi.h,
                scaleX: 1,
                scaleY: 1
            }}));
            
            // Send to Streamlit
            window.parent.postMessage({{
                type: 'streamlit:setComponentValue',
                data: {{objects: roiData}}
            }}, '*');
        }}
        
        // Button event listeners
        document.getElementById('clearBtn').addEventListener('click', function(e) {{
            e.preventDefault();
            clearROIs();
        }});
        
        document.getElementById('undoBtn').addEventListener('click', function(e) {{
            e.preventDefault();
            undoLastROI();
        }});
        
        // Handle window resize
        window.addEventListener('resize', function() {{
            // Redraw to maintain aspect ratio
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            rois.forEach(roi => {{
                ctx.strokeStyle = roi.color;
                ctx.lineWidth = roi.width;
                ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
            }});
        }});
        
        // Initialize with empty data
        sendROIData();
    </script>
    """
    
    return components.html(canvas_html, height=canvas_h + 120, width=canvas_w + 20)

# =====================================================
# IMAGE SOURCE (Upload or Camera)
# =====================================================
st.subheader("Select Image Source")

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

    st.caption(f"Original image size: **{orig_w} × {orig_h}px**")

    # =====================================================
    # SCALE IMAGE FOR CANVAS
    # =====================================================
    MAX_CANVAS_WIDTH = max_canvas_width
    canvas_w = min(orig_w, MAX_CANVAS_WIDTH)
    scale = canvas_w / orig_w
    canvas_h = int(orig_h * scale)

    img_display = img.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)

else:
    st.info("👆 Upload or capture an image to start")
    st.stop()

# =====================================================
# DRAW ROI CANVAS - WITH MOBILE SUPPORT
# =====================================================
st.subheader("Draw ROIs")

# Initialize session state for ROI objects
if 'roi_objects' not in st.session_state:
    st.session_state.roi_objects = []

if is_mobile:
    # Use mobile-optimized canvas
    canvas_result = create_mobile_canvas(img_display, canvas_w, canvas_h, stroke_width, stroke_color)
    
    # Get objects from the canvas component
    if canvas_result and isinstance(canvas_result, dict):
        st.session_state.roi_objects = canvas_result.get("objects", [])
    
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
        key="roi_canvas",
        display_toolbar=True,
    )
    
    # Safe JSON extraction
    objects = []
    if canvas.json_data and "objects" in canvas.json_data:
        objects = canvas.json_data["objects"]
        st.session_state.roi_objects = objects

# Display ROI count
col1, col2, col3 = st.columns(3)
with col1:
    st.info(f"📦 **{len(objects)} ROI(s) drawn**")
with col2:
    if st.button("🗑 Clear All ROIs", use_container_width=True):
        st.session_state.roi_objects = []
        if not is_mobile:
            st.session_state.roi_canvas.json_data = {"objects": []}
        st.rerun()
with col3:
    if st.button("↩ Undo Last ROI", use_container_width=True) and objects:
        st.session_state.roi_objects = objects[:-1]
        if not is_mobile:
            st.session_state.roi_canvas.json_data = {"objects": objects[:-1]}
        st.rerun()

# =====================================================
# RUN PIPELINE
# =====================================================
if st.button("🚀 Run CRAFT + OCR + Restitch", use_container_width=True):

    if not objects:
        st.warning("⚠️ Draw at least one ROI")
        st.stop()

    # -------------------------------------------------
    # CLEAN OLD FILES
    # -------------------------------------------------
    for f in os.listdir(ROI_DIR):
        f_path = os.path.join(ROI_DIR, f)
        if os.path.isfile(f_path) and f.lower().endswith((".jpg", ".png", ".jpeg")):
            os.remove(f_path)

    st.info("🧹 Old ROI data cleared")

    # -------------------------------------------------
    # SAVE ROIs
    # -------------------------------------------------
    saved_count = 0
    for roi_id, obj in enumerate(objects, start=1):
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

    st.success(f"✅ {saved_count} ROI images saved")

    if saved_count == 0:
        st.error("No valid ROIs to process")
        st.stop()

    # -------------------------------------------------
    # RUN CRAFT PIPELINE
    # -------------------------------------------------
    cropped_dir = os.path.join(ROI_DIR, "cropped_boxes")
    if os.path.exists(cropped_dir):
        shutil.rmtree(cropped_dir)

    with st.spinner("🔄 Running CRAFT text detection and OCR..."):
        try:
            subprocess.run(
                [sys.executable, os.path.join(BASE_DIR, "st_sample.py"), ROI_DIR],
                check=True,
                capture_output=True,
                text=True
            )
            st.success("✅ Pipeline completed successfully 🎉")

        except subprocess.CalledProcessError as e:
            st.error("❌ Pipeline failed")
            with st.expander("View error details"):
                st.code(e.stdout if e.stdout else e.stderr)
            st.stop()

    # -------------------------------------------------
    # SHOW OCR OUTPUTS
    # -------------------------------------------------
    output_dir = os.path.join(ROI_DIR, "cropped_boxes", "output")

    if os.path.exists(output_dir):
        st.subheader("📄 OCR Results")
        
        # Display images in a grid
        output_images = sorted([f for f in os.listdir(output_dir) if f.lower().endswith(".jpg")])
        
        if output_images:
            cols = st.columns(3)
            for idx, f in enumerate(output_images):
                with cols[idx % 3]:
                    st.image(
                        os.path.join(output_dir, f),
                        caption=f,
                        use_column_width=True
                    )
        else:
            st.warning("No OCR output images found")
    else:
        st.warning("⚠️ No OCR output found")

    # -------------------------------------------------
    # SHOW STITCHED EXCEL OUTPUT
    # -------------------------------------------------
    stitched_excel_path = os.path.join(ROI_DIR, "stitched", "stitched_output.xlsx")

    if os.path.exists(stitched_excel_path):
        st.subheader("Stitched Excel Output")

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
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
    else:
        st.warning("⚠️ Excel file not found")

# Add instructions for mobile users
if is_mobile:
    with st.expander("📱 Mobile Drawing Instructions"):
        st.markdown("""
        **How to draw ROIs on mobile:**
        1. **Tap** to start drawing a rectangle
        2. **Drag** to draw the rectangle
        3. **Release** to complete the ROI
        4. Use **Clear All** to remove all ROIs
        5. Use **Undo Last** to remove the last ROI
        
        **Tips:**
        - Draw slowly for better accuracy
        - Make sure your ROI is at least 10x10 pixels
        - You can draw multiple ROIs on the same image
        - The ROI color and border width can be adjusted in the sidebar
        """)