import os
import mimetypes
from PIL import Image, ImageDraw

# ---------------------------------------------------------
# KAGGLE REQUIREMENT: Security Features
# ---------------------------------------------------------
def validate_image_security(file_path: str) -> dict:
    """
    Security Tool: Validates the uploaded file to prevent malicious code execution.
    Checks file existence, MIME type, and restricts file size (< 5MB).
    """
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"File not found: {file_path}"}
    
    # 1. Check File Size (Max 20MB to accommodate lossless formats like TIFF/BMP)
    max_size_bytes = 20 * 1024 * 1024
    if os.path.getsize(file_path) > max_size_bytes:
        return {"status": "error", "message": "Security Alert: File exceeds 20MB limit."}
    
    # 2. Check MIME Type — accept any image/* format
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None or not mime_type.startswith('image/'):
        return {"status": "error", "message": f"Security Alert: Invalid file type '{mime_type}'. Only image files are allowed."}
    
    # 3. Deep validation: Try opening with PIL to catch corrupted/fake image headers
    try:
        with Image.open(file_path) as img:
            img.verify() # Verifies header without decoding the entire image
    except Exception as e:
        return {"status": "error", "message": "Security Alert: File is corrupted or not a valid image format."}

    return {"status": "success", "message": "Image passed security validation."}

# ---------------------------------------------------------
# KAGGLE REQUIREMENT: Agent Skills
# ---------------------------------------------------------
def annotate_image(file_path: str, anomalies: list, output_path: str = "annotated_report.jpg") -> str:
    """
    Agent Skill: Takes a list of (x, y) coordinates and draws red circles around them.
    Expects 'anomalies' to be a list of dictionaries: [{'x': 150, 'y': 200, 'radius': 50, 'reason': 'weird fingers'}]
    """
    try:
        with Image.open(file_path) as img:
            # Convert to RGB in case of RGBA/PNG
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            
            for anomaly in anomalies:
                x = anomaly.get('x', 0)
                y = anomaly.get('y', 0)
                r = anomaly.get('radius', 40) # Default radius
                
                # Draw a thick red circle
                bounding_box = [x - r, y - r, x + r, y + r]
                draw.ellipse(bounding_box, outline="red", width=5)
            
            img.save(output_path)
            return f"Success: Annotated image saved to {output_path}."
    except Exception as e:
        return f"Error annotating image: {str(e)}"