import os
import uuid
import base64
import traceback
import asyncio
import aiofiles
import aiohttp
from typing import Annotated
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from bson.objectid import ObjectId

import sys
import io

# Fix for Windows charmap/encoding errors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def safe_str(s):
    if s is None: return ""
    try:
        val = str(s)
        return val.encode('ascii', 'ignore').decode('ascii')
    except Exception:
        return "[non-ascii content]"

from backend.database import presentations_col, media_col, fs
from backend.services import (
    fast_extract_text,
    extract_slides,
    async_generate_script_sarvam,
    async_generate_audio_for_slide,
    async_generate_audience_questions
)

router = APIRouter(prefix="/api/presentations", tags=["presentations"])

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


# ── UPLOAD ──────────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_presentation(
    file: Annotated[UploadFile, File(description="PPTX file to upload")],
    user_id: Annotated[str, Form(description="Firebase user ID")],
    user_email: Annotated[str, Form(description="User email")],
    voice_id: Annotated[str, Form(description="AI voice ID")] = "21m00Tcm4TlvDq8ikWAM",
) -> dict:
    """Upload a PPTX file and extract its slide content."""
    try:
        if not file.filename or not file.filename.lower().endswith((".ppt", ".pptx")):
            raise HTTPException(status_code=400, detail="Only .ppt and .pptx files are supported.")

        presentation_id = str(uuid.uuid4())
        pptx_dir = os.path.join(UPLOADS_DIR, presentation_id)
        os.makedirs(pptx_dir, exist_ok=True)

        safe_filename = os.path.basename(file.filename)

        # Read uploaded PPTX into memory
        content = await file.read()
        print(f"[upload] Received PPTX for {presentation_id} ({len(content)} bytes)")

        # Store the PPTX in GridFS instead of a raw base64 string or an OS file
        pptx_file_id = ""
        try:
            oid = fs.put(content, filename=safe_filename.encode("utf-8", "ignore").decode("utf-8"))
            pptx_file_id = str(oid)
        except Exception as e:
            print(f"[upload] GridFS error: {safe_str(e)}")
            raise HTTPException(status_code=500, detail=f"GridFS error: {safe_str(e)}")

        # Phase 1: FAST extraction (Text only) for instant UI response
        try:
            slides_data = await asyncio.to_thread(fast_extract_text, content)
            print(f"[upload] Fast-extracted {len(slides_data)} slides")
        except Exception as e:
            err_msg = safe_str(e)
            print(f"[upload] Failed to parse PPTX: {err_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to parse PPTX: {err_msg}")

        import datetime

        # Store large media asynchronously and clean up slides_data for main document
        media_docs = []
        clean_slides = []
        for s in slides_data:
            img_uri = s.pop("image_data_uri", None)
            if img_uri:
                media_docs.append({
                    "presentation_id": presentation_id,
                    "slide_number": s["slide_number"],
                    "image_data_uri": img_uri
                })
            clean_slides.append(s)

        if media_docs:
            await asyncio.to_thread(media_col.insert_many, media_docs)

        presentation_doc = {
            "_id": presentation_id,
            "user_id": user_id,
            "user_email": user_email,
            "voice_id": voice_id,
            "title": safe_filename.rsplit(".", 1)[0],
            "filename": safe_filename,
            "pptx_file_id": pptx_file_id,
            "status": "processing",
            "slide_count": len(clean_slides),
            "slides": clean_slides,
            "questions": [],
            "created_at": datetime.datetime.utcnow().isoformat(),
        }

        try:
            await asyncio.to_thread(presentations_col.insert_one, presentation_doc)
            print(f"[upload] Stored presentation {presentation_id} in MongoDB securely")
        except Exception as e:
            err_db = safe_str(e)
            print(f"[upload] Database error: {err_db}")
            raise HTTPException(status_code=500, detail=f"Database error: {err_db}")

        return {
            "presentation_id": presentation_id,
            "title": presentation_doc["title"],
            "slide_count": len(clean_slides),
            "slides": clean_slides,
            "status": "processing",
        }
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        err_simple = safe_str(e)
        try:
            print(f"[upload] Unexpected error: {err_simple}")
            print(safe_str(error_msg))
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Unexpected error: {err_simple}")


# ── GENERATE (triggers background AI processing) ────────────────────────────
@router.post("/{presentation_id}/generate")
def generate_presentation(
    presentation_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger AI script + audio generation for all slides asynchronously."""
    doc = presentations_col.find_one({"_id": presentation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Presentation not found.")

    # Strip legacy huge data before passing to async generator if processing an old presentation
    for slide in doc.get("slides", []):
        slide.pop("image_data_uri", None)
        slide.pop("audio_data_uri", None)
    doc.pop("pptx_base64", None)

    background_tasks.add_task(_process_presentation_async, presentation_id, doc)

    return {"status": "generating", "message": "Presentation generation started asynchronously."}


async def _process_single_slide_async(slide: dict, presentation_id: str, voice_id: str, session: aiohttp.ClientSession):
    """Worker function to process a single slide's script and audio concurrently."""
    slide_num = slide.get("slide_number", "?")
    print(f"[generate] Processing slide {slide_num}")

    # 1. Generate speaking script
    try:
        script = await async_generate_script_sarvam(slide, session)
    except Exception as e:
        print(f"[generate] Script error for slide {slide_num}: {safe_str(e)}")
        title = slide.get("title", f"Slide {slide_num}")
        points = slide.get("points", [])
        script = f"In this slide, we discuss {title.encode('ascii','ignore').decode('ascii')}. " + (
            "Key points: " + "; ".join(points).encode('ascii','ignore').decode('ascii') + "." if points else ""
        )

    slide["script"] = script

    # 2. Generate audio
    try:
        audio_data_uri = await async_generate_audio_for_slide(script, slide_num, presentation_id, voice_id, session)
    except Exception as e:
        print(f"[generate] Audio error for slide {slide_num}: {safe_str(e)}")
        audio_data_uri = None

    if audio_data_uri:
        # Save large base64 audio to media_col
        await asyncio.to_thread(
            media_col.update_one,
            {"presentation_id": presentation_id, "slide_number": slide_num},
            {"$set": {"audio_data_uri": audio_data_uri}},
            upsert=True
        )

    slide["audio_url"] = None
    return slide

async def _process_presentation_async(presentation_id: str, doc: dict) -> None:
    """
    Background task: 
    1. Extract high-fidelity images (Slow COM)
    2. Generate scripts + audio for every slide 
    """
    print(f"[generate] Starting background processing for {safe_str(presentation_id)}")
    
    # Update status to extracting images
    await asyncio.to_thread(
        presentations_col.update_one,
        {"_id": presentation_id},
        {"$set": {"status": "extracting_images"}}
    )
    
    # 1. High-fidelity image extraction
    file_id = doc.get("pptx_file_id")
    if file_id:
        try:
            print(f"[generate] Fetching PPTX from GridFS for {safe_str(presentation_id)}")
            grid_out = fs.get(ObjectId(file_id))
            content = grid_out.read()
            
            print(f"[generate] Extracting slides via PowerPoint COM for {safe_str(presentation_id)}")
            # Full extraction with images
            full_slides = await asyncio.to_thread(extract_slides, content, presentation_id)
            
            # Save images to media_col
            if full_slides:
                print(f"[generate] Updating media collection with {len(full_slides)} images for {safe_str(presentation_id)}")
                for s in full_slides:
                    if s.get("image_data_uri"):
                        await asyncio.to_thread(
                            media_col.update_one,
                            {"presentation_id": presentation_id, "slide_number": s["slide_number"]},
                            {"$set": {"image_data_uri": s["image_data_uri"]}},
                            upsert=True
                        )
                print(f"[generate] Image extraction COMPLETE for {safe_str(presentation_id)}")
            else:
                print(f"[generate] WARNING: full_slides was empty for {safe_str(presentation_id)}")
        except Exception as e:
            print(f"[generate] Image extraction FATAL ERROR: {safe_str(e)}")
            import traceback
            print(safe_str(traceback.format_exc()))

    # Update status to generating audio
    await asyncio.to_thread(
        presentations_col.update_one,
        {"_id": presentation_id},
        {"$set": {"status": "generating_audio"}}
    )

    slides_data = doc.get("slides", [])
    voice_id = doc.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
    
    async with aiohttp.ClientSession() as session:
        # Concurrently process all slides
        tasks = [_process_single_slide_async(s, presentation_id, voice_id, session) for s in slides_data]
        updated_slides = await asyncio.gather(*tasks)

        # 3. Generate audience questions
        try:
            questions = await async_generate_audience_questions(updated_slides, session)
        except Exception as e:
            print(f"[generate] Q&A error: {safe_str(e)}")
            questions = [
                "What are the main takeaways from this presentation?",
                "How does this apply in practice?",
                "What challenges might arise when implementing this?",
                "What is the future direction of this work?",
                "Can you elaborate on the most important point?",
            ]

    # 4. Update MongoDB (main presentation_doc)
    await asyncio.to_thread(
        presentations_col.update_one,
        {"_id": presentation_id},
        {"$set": {
            "slides": updated_slides,
            "questions": questions,
            "status": "ready",
        }}
    )
    print(f"[generate] Presentation {presentation_id} is ready with {len(updated_slides)} slides")


# ── STATUS (Lightweight) ──────────────────────────────────────────────────────
@router.get("/{presentation_id}/status")
def get_presentation_status(presentation_id: str) -> dict:
    """Get metadata and slide titles (very lightweight now)."""
    doc = presentations_col.find_one({"_id": presentation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Presentation not found.")

    return {
        "presentation_id": presentation_id,
        "status": doc.get("status", "unknown"),
        "title": doc.get("title", ""),
        "slide_count": doc.get("slide_count", 0),
        "slides": doc.get("slides", []),
        "questions": doc.get("questions", []),
        "created_at": doc.get("created_at", ""),
    }


# ── SLIDE DETAIL (On-demand) ──────────────────────────────────────────────────
@router.get("/{presentation_id}/slide/{index}")
def get_slide_detail(presentation_id: str, index: int) -> dict:
    """Fetch full image and audio data for a single slide by index (1-based) from media collection."""
    media = media_col.find_one({"presentation_id": presentation_id, "slide_number": index})
    
    if not media:
        # Backwards compatibility check for older data
        doc = presentations_col.find_one(
            {"_id": presentation_id},
            {"slides": {"$slice": [index - 1, 1]}}
        )
        if doc and doc.get("slides"):
            s = doc["slides"][0]
            if s.get("image_data_uri") or s.get("audio_data_uri"):
                return {
                    "image_data_uri": s.get("image_data_uri"),
                    "audio_data_uri": s.get("audio_data_uri")
                }
        raise HTTPException(status_code=404, detail="Slide media not found.")
    
    return {
        "image_data_uri": media.get("image_data_uri"),
        "audio_data_uri": media.get("audio_data_uri")
    }


# ── USER PRESENTATIONS ────────────────────────────────────────────────────────
@router.get("/user/{user_id}")
def get_user_presentations(user_id: str) -> list[dict]:
    """Get all presentations belonging to a user."""
    docs = list(presentations_col.find({"user_id": user_id}, {"slides": 0}))
    result = []
    for doc in docs:
        result.append({
            "id": str(doc.get("_id", "")),
            "title": doc.get("title", ""),
            "status": doc.get("status", ""),
            "slide_count": doc.get("slide_count", 0),
            "created_at": doc.get("created_at", ""),
        })
    return result


# ── DELETE ────────────────────────────────────────────────────────────────────
@router.delete("/{presentation_id}")
def delete_presentation(presentation_id: str, user_id: str) -> dict:
    """Delete a presentation and all associated GridFS/media assets."""
    doc = presentations_col.find_one({"_id": presentation_id, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Presentation not found.")
        
    file_id = doc.get("pptx_file_id")
    if file_id:
        try:
            fs.delete(ObjectId(file_id))
        except Exception as e:
            print(f"[upload] Failed to delete gridfs file: {safe_str(e)}")
            
    media_col.delete_many({"presentation_id": presentation_id})
    presentations_col.delete_one({"_id": presentation_id})
    return {"message": "Presentation deleted successfully."}


# ── OPEN EXACT PPT (LOCAL ONLY) ───────────────────────────────────────────────
@router.post("/{presentation_id}/open_ppt")
def open_pptx_locally(presentation_id: str):
    """Open the exact uploaded PPTX directly in Microsoft PowerPoint (local only)."""
    from bson.objectid import ObjectId
    import tempfile
    
    doc = presentations_col.find_one({"_id": presentation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Presentation not found")
        
    file_id = doc.get("pptx_file_id")
    if not file_id:
        raise HTTPException(status_code=400, detail="PPTX file not found in DB")
        
    try:
        grid_out = fs.get(ObjectId(file_id))
        content = grid_out.read()
        
        # Save to temp file
        temp_dir = os.path.join(os.path.dirname(__file__), "..", "temp_ppt")
        os.makedirs(temp_dir, exist_ok=True)
        safe_title = doc.get('title', 'presentation').replace(' ', '_').replace('/', '')
        temp_path = os.path.join(temp_dir, f"{safe_title}_{presentation_id}.pptx")
        
        with open(temp_path, "wb") as f:
            f.write(content)
            
        # Try to open using win32com to start exactly in Slide Show mode if possible
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            powerpoint.Visible = True
            abs_temp_pptx = os.path.abspath(temp_path)
            presentation = powerpoint.Presentations.Open(abs_temp_pptx)
            
            try:
                presentation.SlideShowSettings.Run()
            except Exception as e:
                print(f"[open_ppt] Failed to start slideshow: {e}")
                
            return {"status": "success", "message": "PowerPoint opened in Slide Show mode"}
        except Exception as e:
            print(f"[open_ppt] win32com fallback: {e}")
            # Fallback to default system opener
            if os.name == 'nt':
                os.startfile(temp_path)
            else:
                import subprocess
                subprocess.Popen(['open', temp_path]) # MacOS fallback
                
            return {"status": "success", "message": "Opened file normally"}
            
    except Exception as e:
        print(f"[open_ppt] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

