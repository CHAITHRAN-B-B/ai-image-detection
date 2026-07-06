import streamlit as st
import streamlit.components.v1 as components
import os
import json
import time
import tempfile
import hashlib
import base64
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

from forensics_tools import annotate_image

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="AI Forensics Neural-Scan",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- CUSTOM COMPONENT SETUP FOR CLIPBOARD COPY-PASTE & DRAG-DROP ---
def create_upload_paste_component():
    """Generates an inline bidirectional component to enable drag-and-drop, browsing, and clipboard image pasting."""
    temp_dir = tempfile.mkdtemp()
    index_path = os.path.join(temp_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <style>
        #drop-zone {
            background: rgba(10, 15, 30, 0.4);
            border: 2px dashed rgba(56, 189, 248, 0.3);
            color: #38bdf8;
            border-radius: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            font-weight: 500;
            padding: 2rem 1rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease-in-out;
            user-select: none;
            box-sizing: border-box;
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        #drop-zone.dragover {
            border-color: #f43f5e;
            background: rgba(244, 63, 94, 0.08);
            box-shadow: 0 0 20px rgba(244, 63, 94, 0.2);
            color: #f43f5e;
        }
        #drop-zone:hover:not(.dragover) {
            border-color: rgba(56, 189, 248, 0.8);
            box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
            background: rgba(56, 189, 248, 0.04);
        }
        #drop-zone .icon {
            font-size: 1.8rem;
        }
        #drop-zone .sub-text {
            color: #64748b;
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        #file-input {
            display: none;
        }
    </style>
</head>
<body>
    <div id="drop-zone">
        <div class="icon">🔬</div>
        <div id="status-text">DRAG & DROP Specimen Image, BROWSE, or PASTE (Ctrl+V) here to engage pipeline</div>
        <div class="sub-text">Accepts PNG, JPEG, WEBP, BMP</div>
    </div>
    <input type="file" id="file-input" accept="image/*" />

    <script>
        function sendMessage(type, data) {
            const message = {
                isStreamlitMessage: true,
                type: type,
                ...data
            };
            window.parent.postMessage(message, "*");
        }

        // Notify Streamlit that the component is ready
        sendMessage("streamlit:componentReady", { apiVersion: 1 });
        sendMessage("streamlit:setFrameHeight", { height: 160 });

        const dropZone = document.getElementById("drop-zone");
        const fileInput = document.getElementById("file-input");
        const statusText = document.getElementById("status-text");

        dropZone.addEventListener("click", () => fileInput.click());

        fileInput.addEventListener("change", (e) => {
            if (e.target.files.length > 0) handleFile(e.target.files[0]);
        });

        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
            statusText.innerText = "DROP IMAGE TO SCAN";
        });

        dropZone.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
            statusText.innerText = "DRAG & DROP Specimen Image, BROWSE, or PASTE (Ctrl+V) here to engage pipeline";
        });

        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
            statusText.innerText = "DRAG & DROP Specimen Image, BROWSE, or PASTE (Ctrl+V) here to engage pipeline";
            if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
        });

        window.addEventListener("paste", (e) => {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf("image") === 0) {
                    const blob = items[i].getAsFile();
                    handleFile(blob, "Pasted Clipboard Image");
                    break;
                }
            }
        });

        function handleFile(file, customName) {
            if (!file.type.startsWith("image/")) {
                statusText.innerText = "❌ File must be an image!";
                setTimeout(() => {
                    statusText.innerText = "DRAG & DROP Specimen Image, BROWSE, or PASTE (Ctrl+V) here to engage pipeline";
                }, 2000);
                return;
            }

            statusText.innerText = "⚡ Loading image...";
            const reader = new FileReader();
            reader.onload = function(event) {
                sendMessage("streamlit:setComponentValue", { value: event.target.result });
                statusText.innerText = "✅ " + (customName || file.name) + " loaded successfully";
                setTimeout(() => {
                    statusText.innerText = "DRAG & DROP Specimen Image, BROWSE, or PASTE (Ctrl+V) here to engage pipeline";
                }, 3000);
            };
            reader.readAsDataURL(file);
        }
    </script>
</body>
</html>
        """)
    return temp_dir

# --- MAGNIFIER HTML GENERATOR ---
def get_magnifier_html(src_b64, res_b64=None):
    """Generates an isolated HTML bundle containing both images and their JS logic safely."""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght=400;600&display=swap');
            body {
                margin: 0;
                padding: 0;
                background: #06070a; /* Matches main app background */
                color: #e2e8f0;
                font-family: 'JetBrains Mono', monospace;
                display: flex;
                justify-content: center;
                gap: 2rem;
            }
            .column {
                display: flex;
                flex-direction: column;
                align-items: center;
                width: 310px;
            }
            .card-label {
                font-size: 0.72rem;
                letter-spacing: 2px;
                color: #38bdf8;
                text-transform: uppercase;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
                justify-content: center;
            }
            .card {
                background: rgba(10, 15, 30, 0.6);
                border: 1px solid rgba(56, 189, 248, 0.15);
                border-radius: 12px;
                padding: 10px;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                display: flex;
                justify-content: center;
                align-items: center;
                width: 310px;
                height: 310px;
                box-sizing: border-box;
                cursor: crosshair;
            }
            .card:hover {
                border-color: rgba(56, 189, 248, 0.4);
                box-shadow: 0 0 20px rgba(56, 189, 248, 0.08);
            }
            .card img {
                max-height: 290px;
                max-width: 290px;
                object-fit: contain;
                border-radius: 6px;
                display: block;
            }
            .lens-overlay {
                position: absolute;
                border: 1px solid rgba(56, 189, 248, 0.8);
                background-color: rgba(56, 189, 248, 0.2);
                width: 100px;
                height: 100px;
                display: none;
                pointer-events: none;
                z-index: 900;
            }
            .zoom-result {
                position: absolute;
                top: calc(100% + 15px);
                left: 0;
                width: 310px;
                height: 310px;
                background-color: #0a0f1e;
                border: 2px solid rgba(56, 189, 248, 0.6);
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.8);
                display: none;
                pointer-events: none;
                background-repeat: no-repeat;
                z-index: 1000;
                box-sizing: border-box;
            }
            .clean-state {
                background: rgba(34,197,94,0.04);
                border: 1px dashed rgba(34,197,94,0.3);
                border-radius: 12px;
                padding: 2.5rem;
                text-align: center;
                width: 310px;
                height: 310px;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .clean-state p { margin: 5px 0; }
        </style>
    </head>
    <body>
        <div class="column">
            <div class="card-label">◈ &nbsp;Source Specimen Input</div>
            <div class="card" id="src-card">
                <img src="data:image/jpeg;base64,__SRC_B64__" id="src-img" />
                <div class="lens-overlay" id="src-lens"></div>
                <div class="zoom-result" id="src-zoom"></div>
            </div>
        </div>
        __RES_COLUMN__
        
        <script>
            const zoom = 2.5;

            function getElements() {
                return {
                    src: {
                        card: document.getElementById("src-card"),
                        img: document.getElementById("src-img"),
                        lens: document.getElementById("src-lens"),
                        zoom: document.getElementById("src-zoom")
                    },
                    res: {
                        card: document.getElementById("res-card"),
                        img: document.getElementById("res-img"),
                        lens: document.getElementById("res-lens"),
                        zoom: document.getElementById("res-zoom")
                    }
                };
            }

            function setDisplay(els, displayMode) {
                if (els.src.card && els.src.lens) els.src.lens.style.display = displayMode;
                if (els.src.card && els.src.zoom) els.src.zoom.style.display = displayMode;
            }

            function updateMagnifier(targetEls, relX, relY, bgImgSrc) {
                if (!targetEls.card || !targetEls.img) return;
                
                const cardRect = targetEls.card.getBoundingClientRect();
                const imgRect = targetEls.img.getBoundingClientRect();

                targetEls.zoom.style.backgroundImage = "url('" + bgImgSrc + "')";
                targetEls.zoom.style.backgroundSize = (imgRect.width * zoom) + "px " + (imgRect.height * zoom) + "px";

                const targetX = relX * imgRect.width;
                const targetY = relY * imgRect.height;

                const imgLeftInCard = imgRect.left - cardRect.left;
                const imgTopInCard = imgRect.top - cardRect.top;

                const lensWidth = targetEls.lens.offsetWidth || 100;
                const lensHeight = targetEls.lens.offsetHeight || 100;

                let lensX = targetX - (lensWidth / 2);
                let lensY = targetY - (lensHeight / 2);

                lensX = Math.max(0, Math.min(lensX, imgRect.width - lensWidth));
                lensY = Math.max(0, Math.min(lensY, imgRect.height - lensHeight));

                targetEls.lens.style.left = `${imgLeftInCard + lensX}px`;
                targetEls.lens.style.top = `${imgTopInCard + lensY}px`;

                const clampedRelX = (lensX + lensWidth / 2) / imgRect.width;
                const clampedRelY = (lensY + lensHeight / 2) / imgRect.height;

                const zW = targetEls.zoom.offsetWidth || 310;
                const zH = targetEls.zoom.offsetHeight || 310;

                const bgX = (clampedRelX * imgRect.width * zoom) - (zW / 2);
                const bgY = (clampedRelY * imgRect.height * zoom) - (zH / 2);

                targetEls.zoom.style.backgroundPosition = `-${bgX}px -${bgY}px`;
            }

            function handleMouseMove(e) {
                const els = getElements();
                if (!els.res.card || !els.src.card) return;

                const card = e.target.closest(".card");
                
                // ONLY trigger if hovering the RIGHT image (res-card)
                if (card && card === els.res.card) {
                    
                    setDisplay(els, "block");

                    const hoveredImg = card.querySelector("img");
                    if (!hoveredImg) return;

                    const imgRect = hoveredImg.getBoundingClientRect();
                    
                    const x = e.clientX - imgRect.left;
                    const y = e.clientY - imgRect.top;
                    const relX = Math.min(Math.max(x / imgRect.width, 0), 1);
                    const relY = Math.min(Math.max(y / imgRect.height, 0), 1);

                    // Update LEFT image (src) magnifier based on hover coordinates
                    const bgSrc = els.src.img.src;
                    updateMagnifier(els.src, relX, relY, bgSrc);
                }
            }

            function handleMouseOut(e) {
                const card = e.target.closest(".card");
                if (card) {
                    const nextEl = e.relatedTarget;
                    if (!nextEl || !nextEl.closest(".card")) {
                        setDisplay(getElements(), "none");
                    }
                }
            }

            document.addEventListener("mousemove", handleMouseMove);
            document.addEventListener("mouseout", handleMouseOut);
            document.addEventListener("mouseleave", function() {
                setDisplay(getElements(), "none");
            });
        </script>
    </body>
    </html>
    """
    
    res_column = ""
    if res_b64:
        res_column = f"""
        <div class="column">
            <div class="card-label">◈ &nbsp;Annotated Forensics Mapping</div>
            <div class="card" id="res-card">
                <img src="data:image/jpeg;base64,{res_b64}" id="res-img" />
                <div class="lens-overlay" id="res-lens"></div>
                <div class="zoom-result" id="res-zoom"></div>
            </div>
        </div>
        """
    else:
        res_column = """
        <div class="column">
            <div class="card-label">◈ &nbsp;Annotated Forensics Mapping</div>
            <div class="clean-state">
                <span style="font-size:3rem">🛡️</span>
                <p style="color:#4ade80;font-weight:600;font-size:1.1rem;font-family:'JetBrains Mono', monospace;">ANALYSIS COMPLETED CLEANLY</p>
                <p style="color:#94a3b8;font-size:0.85rem;font-family:sans-serif;margin:0;">No statistical traces of GAN or diffusion artifacts detected.</p>
            </div>
        </div>
        """
        
    return html_template.replace("__SRC_B64__", src_b64).replace("__RES_COLUMN__", res_column)

# --- GLOBAL CSS (CYBERPUNK NEON METRO THEME) ---
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght=300;400;500;600;700&family=JetBrains+Mono:wght=400;500;600;700&display=swap');

  /* Base Terminal Setup */
  html, body, [data-testid="stAppViewContainer"] {
    background: #06070a;
    color: #e2e8f0;
    font-family: 'Inter', sans-serif;
  }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stSidebar"] { display: none; }

  /* Hero HUD Header */
  .hero-wrap {
    text-align: center;
    padding: 2.5rem 0 1rem;
    position: relative;
  }
  .hero-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.8rem;
    font-weight: 700;
    letter-spacing: -1.5px;
    background: linear-gradient(90deg, #38bdf8 0%, #f43f5e 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 6px;
    line-height: 1.1;
    text-transform: uppercase;
  }
  .hero-sub {
    color: #94a3b8;
    font-size: 0.95rem;
    margin: 0;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }

  /* Active Scanning Overlay Animation */
  .scanline-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 6px;
    z-index: 10;
    animation: scanLaserAnimation 2.2s ease-in-out infinite;
  }

  @keyframes scanLaserAnimation {
    0% { top: 0%; }
    50% { top: 100%; }
    100% { top: 0%; }
  }

  /* Fixed Size Crop Container */
  .fixed-crop-container {
    width: 180px;
    height: 180px;
    flex-shrink: 0;
    border-radius: 8px;
    border: 1px solid rgba(56, 189, 248, 0.3);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(10, 15, 30, 0.6);
  }
  
  .fixed-crop-container img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    border-radius: 8px !important;
  }

  /* Anomaly Flex Row */
  .anomaly-flex-row {
    display: flex;
    align-items: center;
    gap: 2rem;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-left: 4px solid #38bdf8;
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    transition: all 0.25s ease;
  }
  .anomaly-flex-row:hover {
    background: rgba(56, 189, 248, 0.03);
    border-color: rgba(56, 189, 248, 0.25);
    transform: translateX(4px);
  }

  /* ChatGPT Style Typewriter */
  .anomaly-reason-container {
    margin: 0;
    display: block;
    text-align: justify;
    position: relative;
  }

  .anomaly-reason-text {
    font-family: 'JetBrains Mono', monospace !important;
    color: #f1f5f9;
    font-size: 1.4rem;
    font-weight: 500;
    line-height: 1.6;
    display: inline;
    background: linear-gradient(to right, #f1f5f9 100%, transparent 0);
    background-size: 0% 100%;
    background-repeat: no-repeat;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: writeTextEffect 2.2s steps(55, end) forwards;
  }

  @keyframes writeTextEffect {
    to { 
      background-size: 100% 100%; 
      -webkit-text-fill-color: #f1f5f9; 
    }
  }

  .typewriter-cursor-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    background-color: #ffffff;
    border-radius: 50%;
    margin-left: 6px;
    vertical-align: middle;
    box-shadow: 0 0 8px #ffffff;
    animation: blinkCursorEffect 0.6s step-end infinite alternate, hideCursorAfterTyping 0.1s linear 2.2s forwards;
  }

  @keyframes blinkCursorEffect {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  @keyframes hideCursorAfterTyping {
    to { display: none; opacity: 0; }
  }

  /* Styled Metric Cards */
  [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.8rem !important;
    color: #ffffff !important;
    font-weight: 600 !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    color: #94a3b8 !important;
  }

  .card-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 2px;
    color: #38bdf8;
    text-transform: uppercase;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    justify-content: center;
  }
</style>
""", unsafe_allow_html=True)

# --- INIT ---
load_dotenv()
client = genai.Client()

# ─────────────────────────────────────────────
# HERO HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="hero-wrap">
  <h1 class="hero-title">AI IMAGE DETECTION</h1>
  <p class="hero-sub">AI Manipulation Analysis & Cryptographic Deepfake Verification Engine</p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────
# UPLOAD SECTION
# ─────────────────────────────────────────────
with st.columns([1, 2, 1])[1]:
    if "paste_component_dir" not in st.session_state:
        st.session_state["paste_component_dir"] = create_upload_paste_component()
    paste_component = components.declare_component("paste_component", path=st.session_state["paste_component_dir"])
    pasted_image_data = paste_component(key="paste_clipboard_action")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def file_hash(f) -> str:
    f.seek(0)
    h = hashlib.md5(f.read()).hexdigest()
    f.seek(0)
    return h

def convert_to_rgb_jpg(src_path: str) -> str:
    with Image.open(src_path) as img:
        img = img.convert("RGB")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(tmp.name, format="JPEG", quality=95)
        return tmp.name

def get_image_base64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""

def crop_anomaly_regions(image_path: str, anomalies: list) -> list:
    crops = []
    try:
        with Image.open(image_path) as base:
            base = base.convert("RGB")
            w, h = base.size
            for a in anomalies:
                x = a.get("x", 0)
                y = a.get("y", 0)
                r = max(a.get("radius", 40), 30)
                pad = int(r * 0.5)
                side = r + pad
                left   = max(0, x - side)
                top    = max(0, y - side)
                right  = min(w, x + side)
                bottom = min(h, y + side)
                crop = base.crop((left, top, right, bottom))
                crops.append({
                    "image": crop.copy(),
                    "reason": a.get("reason", "Unknown artifact"),
                    "coords": f"X: {x} / Y: {y} [Radius: {r}px]"
                })
    except Exception:
        pass
    return crops

def run_scan(temp_path: str):
    st.session_state["scan_done"] = False
    st.session_state["anomalies"] = []
    st.session_state["result_image"] = None
    st.session_state["scan_time"] = None
    st.session_state["scan_error"] = None

    img_b64 = get_image_base64(temp_path)
    scanner_placeholder = st.empty()

    def render_overlay_animation():
        color = "#38bdf8"
        glow = "rgba(56, 189, 248, 0.35)"
        scanner_placeholder.markdown(f"""
        <div style="text-align: center; margin: 1.5rem 0;">
            <div style="position: relative; display: inline-block; max-height: 360px; border-radius: 12px; overflow: hidden; border: 2px solid {color}; box-shadow: 0 0 25px {glow};">
                <img src="data:image/jpeg;base64,{img_b64}" style="max-height: 360px; display: block; object-fit: contain; opacity: 0.75;" />
                <div class="scanline-overlay" style="background: linear-gradient(90deg, rgba(255,255,255,0) 0%, {color} 50%, rgba(255,255,255,0) 100%); box-shadow: 0 0 15px {color}, 0 0 5px {color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    render_overlay_animation()

    with st.status("🛠️ Core Engine Scanning Engine", expanded=True) as status:
        st.write("🛡️ Validating cryptographic file structures...")
        try:
            with Image.open(temp_path) as img:
                img.verify()
        except Exception as e:
            status.update(label="Critical Security Failure", state="error")
            st.session_state["scan_error"] = f"Unrecognized file architecture: {e}"
            scanner_placeholder.empty()
            return

        try:
            rgb_path = convert_to_rgb_jpg(temp_path)
        except Exception as e:
            status.update(label="Decoding System Terminated", state="error")
            st.session_state["scan_error"] = f"Codec failed: {e}"
            scanner_placeholder.empty()
            return

        st.write("🔍 Activating AI deep-probing models...")
        t_start = time.time()

        try:
            img = Image.open(rgb_path)
            prompt = """
You are an expert AI forensics investigator. Analyse this image to determine if it was generated by AI.
Carefully examine: hands/fingers, skin texture, hair strands, background coherence, lighting consistency,
clothing edges, and facial symmetry for telltale AI generation artifacts.

Respond with a JSON array of anomaly objects. Each object must have exactly:
- "x": integer (pixel X coordinate of anomaly centre)
- "y": integer (pixel Y coordinate of anomaly centre)
- "radius": integer (estimated anomaly size in pixels, minimum 30)
- "reason": string (concise description of what looks AI-generated)

If the image appears authentic, respond with an empty array: []
"""
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            anomalies = json.loads(response.text)
            if not isinstance(anomalies, list):
                anomalies = []
        except (json.JSONDecodeError, Exception) as e:
            st.warning(f"Engine parsing failure, raw response fallback: {e}")
            anomalies = []

        elapsed = round(time.time() - t_start, 2)

        st.write("📝 Marking visual coordinates...")
        output_image_path = None
        if anomalies:
            output_image_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
            annotate_image(rgb_path, anomalies, output_image_path)
            status.update(label="SCAN VERDICT: AI MANIPULATIONS ISOLATED", state="complete")
        else:
            status.update(label="SCAN VERDICT: STRUCTURAL INTEGRITY PASSED", state="complete")

    scanner_placeholder.empty()

    st.session_state["anomalies"] = anomalies
    st.session_state["scan_time"] = elapsed
    st.session_state["result_image"] = output_image_path
    st.session_state["scan_done"] = True

# ─────────────────────────────────────────────
# MAIN PANEL CONTROL
# ─────────────────────────────────────────────
if pasted_image_data:
    try:
        header, encoded = pasted_image_data.split(",", 1)
        file_bytes = base64.b64decode(encoded)
        paste_hash = hashlib.md5(file_bytes).hexdigest()
        
        if st.session_state.get("last_paste_hash") != paste_hash:
            st.session_state["last_paste_hash"] = paste_hash
            suffix = ".png"
            if "jpeg" in header or "jpg" in header:
                suffix = ".jpg"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(file_bytes)
            tmp.flush()
            tmp.close()
            st.session_state["temp_path"] = tmp.name
            st.session_state["last_file_hash"] = paste_hash
            st.session_state["scan_done"] = False
    except Exception as e:
        st.error(f"Failed to process image: {e}")

if "temp_path" in st.session_state:
    temp_path = st.session_state["temp_path"]

    if not st.session_state.get("scan_done", False):
        run_scan(temp_path)

    anomalies    = st.session_state.get("anomalies", [])
    scan_time    = st.session_state.get("scan_time", None)
    result_image = st.session_state.get("result_image", None)
    scan_error   = st.session_state.get("scan_error", None)

    st.markdown("<br>", unsafe_allow_html=True)

    if scan_error:
        st.error(f"🚨 SYSTEM EXCEPTION: {scan_error}")
    else:
        # ── METRIC READOUT row ──
        verdict_label = "AI GENERATED" if anomalies else "REAL"
        m1, m2, m3 = st.columns(3)
        m1.metric("Anomalies Isolated", f"{len(anomalies)} Found",help="Number of AI artifacts detected")
        m2.metric("Scan Verdict", verdict_label,help="Result of analysis")
        m3.metric("Neural Pipeline Latency", f"{scan_time}s" if scan_time else "—",help="Time taken to scan")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── NEW: ISOLATED HTML COMPONENT FOR MAGNIFIER LENS ──
        src_b64 = get_image_base64(temp_path)
        res_b64 = None
        if result_image and os.path.exists(result_image):
            res_b64 = get_image_base64(result_image)
            
        html_str = get_magnifier_html(src_b64, res_b64)
        
        # FIX: Must use components.html to ensure iframe sandboxing so Streamlit doesn't strip the javascript!
        components.html(html_str, height=350, scrolling=False)


        # ── VERTICAL ANOMALY TIMELINE STRIPS ──
        if anomalies and result_image and os.path.exists(result_image):
            st.markdown("<br>", unsafe_allow_html=True)
            st.divider()
            st.markdown(
                '<div class="card-label" style="justify-content: start;">◈ &nbsp;Vertical Evidence Breakdown & Anomaly Chronology</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='color:#94a3b8;font-size:0.85rem;margin-bottom:1.5rem;font-family: JetBrains Mono, monospace;'>"
                f"Isolated {len(anomalies)} structural region(s) showing physical inconsistencies:</p>",
                unsafe_allow_html=True,
            )

            crops = crop_anomaly_regions(result_image, anomalies)

            for idx, crop_data in enumerate(crops):
                tmp_crop = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                crop_data["image"].save(tmp_crop.name, format="JPEG", quality=92)
                tmp_crop.close()

                crop_b64 = get_image_base64(tmp_crop.name)
                st.markdown(f"""
                <div class="anomaly-flex-row">
                  <div class="fixed-crop-container">
                    <img src="data:image/jpeg;base64,{crop_b64}" />
                  </div>
                  <div class="anomaly-reason-container">
                    <span class="anomaly-reason-text">{crop_data['reason']}</span>
                    <span class="typewriter-cursor-dot"></span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="empty-state">
      <div class="empty-icon" style="color: #38bdf8; animation: pulseGlow 1.5s infinite alternate; text-align: center; font-size: 3rem; margin-top: 4rem;">🔬</div>
      <p class="empty-text" style="font-family: 'JetBrains Mono', monospace; color: #64748b; letter-spacing: 1px; text-align: center;">UPLOAD SYSTEM ARCHIVE ABOVE TO ENGAGE PIPELINE</p>
    </div>
    """, unsafe_allow_html=True)
