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
import json

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
        margin-bottom: 10px;
        flex-wrap: wrap;
    }
    
    .roi-button {
        background-color: #ff4b4b;
        color: white;
        border: none;
        padding: 12px 20px;
        border-radius: 5px;
        cursor: pointer;
        font-size: 16px;
        flex: 1;
        min-width: 120px;
        font-weight: bold;
    }
    
    .roi-button:hover {
        background-color: #ff3333;
    }
    
    #clearBtn {
        background-color: #dc3545;
    }
    
    #undoBtn {
        background-color: #6c757d;
    }
    
    .roi-count {
        background-color: #f0f2f6;
        padding: 12px;
        border-radius: 5px;
        text-align: center;
        font-weight: bold;
        font-size: 16px;
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
    
    
def create_mobile_canvas(img_display, canvas_w, canvas_h, stroke_width, stroke_color, component_key):
    """Create a simple mobile-optimized canvas with touch support"""
    
    img_data_url = get_image_data_url(img_display)
    
    # Create a unique ID for this canvas instance
    canvas_id = f"simple_canvas_{component_key}"
    
    canvas_html = f"""
    <div style="width: 100%; max-width: {canvas_w}px; margin: 0 auto;">
        <div style="position: relative; width: {canvas_w}px; height: {canvas_h}px; border: 2px solid #ff4b4b; border-radius: 8px; overflow: hidden;">
            <canvas id="{canvas_id}" width="{canvas_w}" height="{canvas_h}" 
                    style="display: block; width: 100%; height: 100%; touch-action: none; background-color: #f0f2f6;">
            </canvas>
        </div>
        
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button onclick="clearROIs()" style="flex: 1; padding: 15px; background-color: #dc3545; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold;">🗑 Clear All</button>
            <button onclick="undoROI()" style="flex: 1; padding: 15px; background-color: #6c757d; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold;">↩ Undo</button>
        </div>
        
        <div id="roiDisplay" style="margin-top: 15px; padding: 15px; background-color: #e8f0fe; border-radius: 8px; text-align: center; font-size: 18px; font-weight: bold; color: #1f1f1f;">
            📦 ROIs: <span id="roiCount">0</span>
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
            
            // Load image
            img.onload = function() {{
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                drawROIs();
            }};
            
            // Draw all ROIs
            function drawROIs() {{
                rois.forEach(roi => {{
                    ctx.strokeStyle = '{stroke_color}';
                    ctx.lineWidth = {stroke_width};
                    ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
                    
                    // Add label
                    ctx.fillStyle = '{stroke_color}';
                    ctx.font = 'bold 14px Arial';
                    ctx.fillText(`ROI ${{roi.id}}`, roi.x + 5, roi.y - 5);
                }});
                
                document.getElementById('roiCount').innerText = rois.length;
            }}
            
            // Drawing state
            let drawing = false;
            let startX, startY;
            
            // Touch events
            canvas.addEventListener('touchstart', (e) => {{
                e.preventDefault();
                const rect = canvas.getBoundingClientRect();
                const x = (e.touches[0].clientX - rect.left) * (canvas.width / rect.width);
                const y = (e.touches[0].clientY - rect.top) * (canvas.height / rect.height);
                
                drawing = true;
                startX = x;
                startY = y;
            }});
            
            canvas.addEventListener('touchmove', (e) => {{
                e.preventDefault();
                if (!drawing) return;
                
                const rect = canvas.getBoundingClientRect();
                const x = (e.touches[0].clientX - rect.left) * (canvas.width / rect.width);
                const y = (e.touches[0].clientY - rect.top) * (canvas.height / rect.height);
                
                // Redraw
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                drawROIs();
                
                // Draw current rectangle
                ctx.strokeStyle = '{stroke_color}';
                ctx.lineWidth = {stroke_width};
                ctx.strokeRect(startX, startY, x - startX, y - startY);
            }});
            
            canvas.addEventListener('touchend', (e) => {{
                e.preventDefault();
                if (!drawing) return;
                
                const rect = canvas.getBoundingClientRect();
                const x = (e.changedTouches[0].clientX - rect.left) * (canvas.width / rect.width);
                const y = (e.changedTouches[0].clientY - rect.top) * (canvas.height / rect.height);
                
                const width = x - startX;
                const height = y - startY;
                
                if (Math.abs(width) > 20 && Math.abs(height) > 20) {{
                    const roi = {{
                        id: rois.length + 1,
                        x: width > 0 ? startX : x,
                        y: height > 0 ? startY : y,
                        w: Math.abs(width),
                        h: Math.abs(height)
                    }};
                    
                    rois.push(roi);
                    
                    // Send to Streamlit
                    const roiData = rois.map(r => ({{
                        left: Math.round(r.x),
                        top: Math.round(r.y),
                        width: Math.round(r.w),
                        height: Math.round(r.h),
                        scaleX: 1,
                        scaleY: 1
                    }}));
                    
                    // Store in sessionStorage
                    sessionStorage.setItem('streamlit_rois', JSON.stringify(roiData));
                    
                    // Trigger Streamlit update
                    if (window.Streamlit) {{
                        window.Streamlit.setComponentValue(roiData);
                    }}
                }}
                
                // Redraw
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                drawROIs();
                drawing = false;
            }});
            
            canvas.addEventListener('touchcancel', (e) => {{
                e.preventDefault();
                drawing = false;
            }});
            
            // Clear function
            window.clearROIs = function() {{
                rois = [];
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                document.getElementById('roiCount').innerText = '0';
                sessionStorage.setItem('streamlit_rois', '[]');
                if (window.Streamlit) {{
                    window.Streamlit.setComponentValue([]);
                }}
            }};
            
            // Undo function
            window.undoROI = function() {{
                rois.pop();
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                drawROIs();
                
                const roiData = rois.map(r => ({{
                    left: Math.round(r.x),
                    top: Math.round(r.y),
                    width: Math.round(r.w),
                    height: Math.round(r.h),
                    scaleX: 1,
                    scaleY: 1
                }})));
                
                sessionStorage.setItem('streamlit_rois', JSON.stringify(roiData));
                if (window.Streamlit) {{
                    window.Streamlit.setComponentValue(roiData);
                }}
            }};
            
            // Initialize Streamlit component
            if (window.Streamlit) {{
                window.Streamlit.setComponentReady();
            }}
            
            // Check for existing ROIs
            const savedROIs = sessionStorage.getItem('streamlit_rois');
            if (savedROIs) {{
                try {{
                    const parsed = JSON.parse(savedROIs);
                    if (parsed && parsed.length > 0) {{
                        rois = parsed.map((r, index) => ({{
                            id: index + 1,
                            x: r.left,
                            y: r.top,
                            w: r.width,
                            h: r.height
                        }}));
                        setTimeout(() => {{
                            ctx.clearRect(0, 0, canvas.width, canvas.height);
                            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                            drawROIs();
                        }}, 100);
                    }}
                }} catch(e) {{}}
            }}
        }})();
    </script>
    """
    
    components.html(canvas_html, height=canvas_h + 150, width=canvas_w + 20)
    
    # Try to load ROIs from sessionStorage
    try:
        import json
        import streamlit as st
        from streamlit.web.server.websocket_headers import _get_headers
        
        # Check if we have ROIs in session state from previous runs
        saved_rois = st.session_state.get('_temp_rois', None)
        if saved_rois:
            st.session_state.roi_objects = saved_rois
            st.session_state._temp_rois = None
    except:
        pass
    
    return None

# def create_mobile_canvas(img_display, canvas_w, canvas_h, stroke_width, stroke_color, component_key):
#     """Create a mobile-optimized canvas with touch support"""
    
#     img_data_url = get_image_data_url(img_display)
    
#     # Get existing ROIs from session state
#     existing_rois = st.session_state.get('roi_objects', [])
#     existing_rois_json = json.dumps(existing_rois)
    
#     canvas_html = f"""
#     <div style="width: 100%; max-width: {canvas_w}px; margin: 0 auto;">
#         <div id="canvas-component-wrapper-{component_key}">
#             <div class="canvas-container" style="position: relative; width: {canvas_w}px; height: {canvas_h}px;">
#                 <canvas id="roiCanvas_{component_key}" width="{canvas_w}" height="{canvas_h}" 
#                         style="display: block; width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; background-color: #f8f9fa;">
#                 </canvas>
#             </div>
            
#             <div class="roi-controls">
#                 <button id="clearBtn_{component_key}" class="roi-button" style="background-color: #dc3545;">🗑 Clear All</button>
#                 <button id="undoBtn_{component_key}" class="roi-button" style="background-color: #6c757d;">↩ Undo Last</button>
#             </div>
            
#             <div id="roiCount_{component_key}" class="roi-count">
#                 ROIs: <span id="roiCountValue_{component_key}">0</span>
#             </div>
#         </div>
#     </div>
    
#     <script>
#         (function() {{
#             // Get canvas element
#             const canvas = document.getElementById('roiCanvas_{component_key}');
#             const ctx = canvas.getContext('2d');
#             const img = new Image();
#             img.crossOrigin = 'Anonymous';
#             img.src = '{img_data_url}';
            
#             // State management
#             let rois = [];
#             let isDrawing = false;
#             let startX, startY;
            
#             // Load existing ROIs from session state
#             try {{
#                 const existingRois = {existing_rois_json};
#                 if (existingRois && existingRois.length > 0) {{
#                     rois = existingRois.map((roi, index) => ({{
#                         id: Date.now() + index + Math.random(),
#                         left: Number(roi.left) || 0,
#                         top: Number(roi.top) || 0,
#                         width: Number(roi.width) || 0,
#                         height: Number(roi.height) || 0,
#                         scaleX: 1,
#                         scaleY: 1,
#                         color: '{stroke_color}',
#                         stroke_width: {stroke_width}
#                     }}));
#                 }}
#             }} catch (e) {{
#                 console.error('Error parsing existing ROIs:', e);
#                 rois = [];
#             }}
            
#             // Load image and draw
#             img.onload = function() {{
#                 ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
#                 drawAllROIs();
#                 updateROICount();
#                 sendROIData();
#             }};
            
#             // Handle image loading errors
#             img.onerror = function() {{
#                 console.error('Failed to load image');
#                 ctx.fillStyle = '#f8f9fa';
#                 ctx.fillRect(0, 0, canvas.width, canvas.height);
#                 ctx.fillStyle = '#dc3545';
#                 ctx.font = '14px Arial';
#                 ctx.fillText('Failed to load image', 10, 50);
#                 sendROIData();
#             }};
            
#             // Draw all ROIs
#             function drawAllROIs() {{
#                 ctx.clearRect(0, 0, canvas.width, canvas.height);
#                 if (img.complete && img.naturalHeight > 0) {{
#                     ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
#                 }}
                
#                 rois.forEach(roi => {{
#                     ctx.strokeStyle = roi.color;
#                     ctx.lineWidth = roi.stroke_width;
#                     ctx.strokeRect(roi.left, roi.top, roi.width, roi.height);
                    
#                     // Draw corner handles
#                     ctx.fillStyle = 'white';
#                     ctx.strokeStyle = 'black';
#                     ctx.lineWidth = 1;
#                     ctx.fillRect(roi.left + roi.width - 5, roi.top + roi.height - 5, 10, 10);
#                     ctx.strokeRect(roi.left + roi.width - 5, roi.top + roi.height - 5, 10, 10);
#                 }});
#             }}
            
#             // Touch events for mobile
#             canvas.addEventListener('touchstart', handleStart, {{ passive: false }});
#             canvas.addEventListener('touchmove', handleMove, {{ passive: false }});
#             canvas.addEventListener('touchend', handleEnd, {{ passive: false }});
#             canvas.addEventListener('touchcancel', handleEnd, {{ passive: false }});
            
#             // Mouse events for desktop
#             canvas.addEventListener('mousedown', handleStart);
#             canvas.addEventListener('mousemove', handleMove);
#             canvas.addEventListener('mouseup', handleEnd);
#             canvas.addEventListener('mouseout', handleEnd);
            
#             // Get coordinates relative to canvas
#             function getEventPosition(e) {{
#                 const rect = canvas.getBoundingClientRect();
#                 const scaleX = canvas.width / rect.width;
#                 const scaleY = canvas.height / rect.height;
                
#                 let clientX, clientY;
                
#                 if (e.touches) {{
#                     clientX = e.touches[0].clientX;
#                     clientY = e.touches[0].clientY;
#                 }} else {{
#                     clientX = e.clientX;
#                     clientY = e.clientY;
#                 }}
                
#                 let x = (clientX - rect.left) * scaleX;
#                 let y = (clientY - rect.top) * scaleY;
                
#                 x = Math.max(0, Math.min(x, canvas.width));
#                 y = Math.max(0, Math.min(y, canvas.height));
                
#                 return {{ x, y }};
#             }}
            
#             // Start drawing
#             function handleStart(e) {{
#                 e.preventDefault();
#                 e.stopPropagation();
                
#                 const pos = getEventPosition(e);
#                 isDrawing = true;
#                 startX = pos.x;
#                 startY = pos.y;
#             }}
            
#             // Draw rectangle
#             function handleMove(e) {{
#                 e.preventDefault();
#                 e.stopPropagation();
                
#                 if (!isDrawing) return;
                
#                 const pos = getEventPosition(e);
                
#                 // Redraw canvas
#                 drawAllROIs();
                
#                 // Draw current rectangle
#                 const width = pos.x - startX;
#                 const height = pos.y - startY;
                
#                 ctx.strokeStyle = '{stroke_color}';
#                 ctx.lineWidth = {stroke_width};
#                 ctx.strokeRect(startX, startY, width, height);
                
#                 // Show dimensions
#                 ctx.fillStyle = '#000000';
#                 ctx.font = '12px Arial';
#                 ctx.fillText(`${{Math.abs(Math.round(width))}}x${{Math.abs(Math.round(height))}}`, 
#                             pos.x + 10, pos.y + 10);
#             }}
            
#             // Stop drawing and save ROI
#             function handleEnd(e) {{
#                 e.preventDefault();
#                 e.stopPropagation();
                
#                 if (!isDrawing) return;
                
#                 const pos = getEventPosition(e);
#                 const width = pos.x - startX;
#                 const height = pos.y - startY;
                
#                 // Only save if rectangle is large enough
#                 if (Math.abs(width) > 10 && Math.abs(height) > 10) {{
#                     const roi = {{
#                         id: Date.now() + Math.random(),
#                         left: Math.round(width > 0 ? startX : pos.x),
#                         top: Math.round(height > 0 ? startY : pos.y),
#                         width: Math.round(Math.abs(width)),
#                         height: Math.round(Math.abs(height)),
#                         scaleX: 1,
#                         scaleY: 1
#                     }};
                    
#                     rois.push(roi);
#                     updateROICount();
#                     sendROIData();
#                 }}
                
#                 drawAllROIs();
#                 isDrawing = false;
#             }}
            
#             // Clear all ROIs
#             function clearROIs() {{
#                 rois = [];
#                 drawAllROIs();
#                 updateROICount();
#                 sendROIData();
#             }}
            
#             // Undo last ROI
#             function undoLastROI() {{
#                 rois.pop();
#                 drawAllROIs();
#                 updateROICount();
#                 sendROIData();
#             }}
            
#             // Update ROI count display
#             function updateROICount() {{
#                 const countElement = document.getElementById('roiCountValue_{component_key}');
#                 if (countElement) {{
#                     countElement.innerText = rois.length;
#                 }}
#             }}
            
#             // Send ROI data to Streamlit
#             function sendROIData() {{
#                 const roiData = rois.map(roi => ({{
#                     left: roi.left,
#                     top: roi.top,
#                     width: roi.width,
#                     height: roi.height,
#                     scaleX: 1,
#                     scaleY: 1
#                 }}));
                
#                 // Create a hidden input to store the data
#                 let input = document.getElementById('roi_data_{component_key}');
#                 if (!input) {{
#                     input = document.createElement('input');
#                     input.type = 'hidden';
#                     input.id = 'roi_data_{component_key}';
#                     input.name = 'roi_data_{component_key}';
#                     document.body.appendChild(input);
#                 }}
                
#                 // Store data as JSON string
#                 input.value = JSON.stringify(roiData);
                
#                 // Dispatch change event
#                 input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
#                 // Also try Streamlit's component communication
#                 if (window.Streamlit) {{
#                     window.Streamlit.setComponentValue(roiData);
#                 }}
                
#                 console.log('Sent ROI data:', roiData.length, 'ROIs');
#             }}
            
#             // Button event listeners
#             document.getElementById('clearBtn_{component_key}').addEventListener('click', function(e) {{
#                 e.preventDefault();
#                 clearROIs();
#             }});
            
#             document.getElementById('undoBtn_{component_key}').addEventListener('click', function(e) {{
#                 e.preventDefault();
#                 undoLastROI();
#             }});
            
#             // Set up Streamlit connection
#             if (window.Streamlit) {{
#                 window.Streamlit.setComponentReady();
#             }}
            
#             // Send initial data
#             setTimeout(() => {{
#                 sendROIData();
#             }}, 500);
            
#             // Create mutation observer to detect changes
#             const observer = new MutationObserver(function(mutations) {{
#                 mutations.forEach(function(mutation) {{
#                     if (mutation.type === 'attributes' && mutation.attributeName === 'value') {{
#                         // Data changed, Streamlit should pick it up
#                     }}
#                 }});
#             }});
            
#             // Observe the hidden input
#             setTimeout(() => {{
#                 const input = document.getElementById('roi_data_{component_key}');
#                 if (input) {{
#                     observer.observe(input, {{ attributes: true }});
#                 }}
#             }}, 100);
#         }})();
#     </script>
#     """
    
#     # Use components.html
#     components.html(
#         canvas_html, 
#         height=canvas_h + 150, 
#         width=canvas_w + 20
#     )
    
#     # Return None - we'll handle the data through session state
#     return None

# =====================================================
# IMAGE SOURCE (Upload or Camera)
# =====================================================
st.subheader("Select Image Source")

# Initialize session state for ROI objects if not exists
if 'roi_objects' not in st.session_state:
    st.session_state.roi_objects = []
if 'canvas_key' not in st.session_state:
    st.session_state.canvas_key = 0

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

# Check for ROI data from form submission (for mobile canvas) - COMPATIBLE VERSION
if is_mobile:
    # Try to get ROI data from various sources
    try:
        # Try query params if available (newer Streamlit)
        if hasattr(st, 'query_params'):
            roi_data = st.query_params.get("roi_data")
            if roi_data:
                import json
                try:
                    new_rois = json.loads(roi_data)
                    if new_rois and len(new_rois) > 0:
                        st.session_state.roi_objects = new_rois
                    if hasattr(st.query_params, 'clear'):
                        st.query_params.clear()
                except:
                    pass
    except:
        pass

# Add reset button for canvas
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Reset Canvas", use_container_width=True):
        st.session_state.roi_objects = []
        st.session_state.canvas_key += 1
        st.rerun()

if is_mobile:
    # Use mobile-optimized canvas
    create_mobile_canvas(
        img_display, 
        canvas_w, 
        canvas_h, 
        stroke_width, 
        stroke_color,
        st.session_state.canvas_key
    )
    
    # Add a button to manually check for ROIs from session storage
    col1, col2, col3 = st.columns(3)
    with col2:
        if st.button("🔄 Load ROIs from Canvas", use_container_width=True):
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

# Display ROI count and controls
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

with col1:
    roi_count = len(st.session_state.roi_objects)
    st.info(f"📦 **{roi_count} ROI(s) drawn**")
    
    # Debug display
    with st.expander("Debug: View ROI Data"):
        st.json(st.session_state.roi_objects)

with col2:
    if st.button("🗑 Clear All", use_container_width=True):
        st.session_state.roi_objects = []
        st.session_state.canvas_key += 1
        st.rerun()

with col3:
    if st.button("↩ Undo Last", use_container_width=True) and st.session_state.roi_objects:
        st.session_state.roi_objects = st.session_state.roi_objects[:-1]
        st.session_state.canvas_key += 1
        st.rerun()

with col4:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# Keep the manual ROI entry as a fallback
if is_mobile:
    with st.expander("📝 Manual ROI Entry (Fallback)", expanded=False):
        st.markdown("If drawing doesn't work, use this fallback method:")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            x1 = st.number_input("X1", 0, canvas_w, 0, key=f"manual_x1_{st.session_state.canvas_key}")
        with col2:
            y1 = st.number_input("Y1", 0, canvas_h, 0, key=f"manual_y1_{st.session_state.canvas_key}")
        with col3:
            x2 = st.number_input("X2", 0, canvas_w, canvas_w, key=f"manual_x2_{st.session_state.canvas_key}")
        with col4:
            y2 = st.number_input("Y2", 0, canvas_h, canvas_h, key=f"manual_y2_{st.session_state.canvas_key}")
        
        if st.button("➕ Add Manual ROI", use_container_width=True, key=f"add_manual_{st.session_state.canvas_key}"):
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

# Display ROI count and controls
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

with col1:
    roi_count = len(st.session_state.roi_objects)
    st.info(f"📦 **{roi_count} ROI(s) drawn**")
    
    # Debug display
    with st.expander("Debug: View ROI Data"):
        st.json(st.session_state.roi_objects)

with col2:
    if st.button("🗑 Clear All", use_container_width=True):
        st.session_state.roi_objects = []
        st.session_state.canvas_key += 1
        st.rerun()

with col3:
    if st.button("↩ Undo Last", use_container_width=True) and st.session_state.roi_objects:
        st.session_state.roi_objects = st.session_state.roi_objects[:-1]
        st.session_state.canvas_key += 1
        st.rerun()

with col4:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# Add a JavaScript-based workaround for mobile
if is_mobile:
    # Add this near the top of your file, after st.set_page_config()
    st.markdown("""
    <script>
    // Periodically check for ROIs in sessionStorage and update Streamlit
    setInterval(function() {
        const rois = sessionStorage.getItem('streamlit_rois');
        if (rois) {
            try {
                const roiData = JSON.parse(rois);
                if (roiData && roiData.length > 0) {
                    // Store in window object for Streamlit to pick up
                    window._streamlit_rois = roiData;
                }
            } catch(e) {}
        }
    }, 1000);
    </script>
    """, unsafe_allow_html=True)

# =====================================================
# RUN PIPELINE
# =====================================================
if st.button("🚀 Run CRAFT + OCR + Restitch", use_container_width=True, type="primary"):

    if not st.session_state.roi_objects:
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
            result = subprocess.run(
                [sys.executable, os.path.join(BASE_DIR, "st_sample.py"), ROI_DIR],
                check=True,
                capture_output=True,
                text=True
            )
            st.success("✅ Pipeline completed successfully 🎉")
            
            # Show output if any
            if result.stdout:
                with st.expander("View pipeline output"):
                    st.code(result.stdout)

        except subprocess.CalledProcessError as e:
            st.error("❌ Pipeline failed")
            with st.expander("View error details"):
                st.code(e.stdout if e.stdout else e.stderr)
            st.stop()
        except FileNotFoundError:
            st.error(f"❌ Could not find st_sample.py at {os.path.join(BASE_DIR, 'st_sample.py')}")
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
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
    else:
        st.warning("⚠️ Excel file not found")

# Add instructions for mobile users
if is_mobile:
    with st.expander("📱 Mobile Drawing Instructions"):
        st.markdown("""
        **How to draw ROIs on mobile:**
        1. **Tap and hold** to start drawing a rectangle
        2. **Drag** to draw the rectangle
        3. **Release** to complete the ROI
        4. The ROI count should increase immediately
        5. Use **Clear All** to remove all ROIs
        6. Use **Undo Last** to remove the last ROI
        7. Use **Refresh** if ROIs don't appear
        
        **Troubleshooting:**
        - If ROIs aren't saving, tap the **Refresh** button
        - Check the Debug section to see if ROI data is captured
        - Make sure your ROI is at least 10x10 pixels
        - Try drawing slower for better accuracy
        """)