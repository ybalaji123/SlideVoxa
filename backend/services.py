import os
import json
import base64
import aiohttp
import asyncio
from pptx import Presentation
from pptx.util import Inches
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import sys
import io

def safe_str(s):
    """Sanitize string for safe printing on Windows console."""
    if s is None: return ""
    try:
        # Get string representation
        val = str(s)
        # Encode to bytes using 'ascii' and 'replace' to handle non-ascii safely
        # Then decode back to string. This is the safest way to prevent charmap errors.
        return val.encode('ascii', 'replace').decode('ascii')
    except Exception:
        return "[sanitization failed]"

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
ELEVENLABS_API_KEY = os.getenv("Eleven_Labs", "").strip()

print(f"[services] SARVAM key loaded: {'YES' if SARVAM_API_KEY else 'MISSING'}")
print(f"[services] ElevenLabs key loaded: {'YES' if ELEVENLABS_API_KEY else 'MISSING'}")


import io
import tempfile
import shutil
import subprocess
import re

def fast_extract_text(content: bytes) -> list[dict]:
    """Extremely fast text extraction using python-pptx (milliseconds)."""
    try:
        b = io.BytesIO(content)
        prs = Presentation(b)
        slides_data = []
        for i, slide in enumerate(prs.slides, 1):
            title = ""
            points = []
            for shape in slide.shapes:
                if not shape.has_text_frame: continue
                text = shape.text_frame.text.strip()
                if not text: continue
                if getattr(shape, "is_placeholder", False) and shape.placeholder_format.idx in (0, 1):
                    title = text
                    continue
                for para in shape.text_frame.paragraphs:
                    if para.text.strip(): points.append(para.text.strip())

            slides_data.append({
                "slide_number": i,
                "title": title or f"Slide {i}",
                "points": list(dict.fromkeys(points))[:10], # Limit points for speed
                "body": "", # Filled later if needed
                "image_data_uri": None
            })
        return slides_data
    except Exception as e:
        print(f"[fast_extract] Failed: {safe_str(e)}")
        return []

def _render_pptx_with_libreoffice(temp_pptx: str, temp_dir: str, slide_count: int) -> dict[int, str]:
    """Render each PPTX slide through LibreOffice and Poppler on Linux hosts."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        raise RuntimeError("Slide rendering needs LibreOffice Impress and Poppler (pdftoppm).")

    pdf_dir = os.path.join(temp_dir, "pdf")
    os.makedirs(pdf_dir, exist_ok=True)
    profile_dir = os.path.join(temp_dir, "lo-profile")
    profile_uri = "file://" + os.path.abspath(profile_dir)
    convert = subprocess.run(
        [soffice, "--headless", f"-env:UserInstallation={profile_uri}", "--convert-to", "pdf", "--outdir", pdf_dir, temp_pptx],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    pdf_path = os.path.join(pdf_dir, os.path.splitext(os.path.basename(temp_pptx))[0] + ".pdf")
    if convert.returncode != 0 or not os.path.isfile(pdf_path):
        raise RuntimeError(f"LibreOffice could not convert the presentation: {safe_str(convert.stderr or convert.stdout)}")

    image_prefix = os.path.join(temp_dir, "slide")
    render = subprocess.run(
        [pdftoppm, "-png", "-r", "144", "-f", "1", "-l", str(slide_count), pdf_path, image_prefix],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    image_paths = sorted(
        (os.path.join(temp_dir, name) for name in os.listdir(temp_dir) if re.fullmatch(r"slide-\d+\.png", name)),
        key=lambda path: int(os.path.basename(path).rsplit("-", 1)[1].split(".", 1)[0]),
    )
    if render.returncode != 0 or not image_paths:
        raise RuntimeError(f"Poppler could not render the presentation: {safe_str(render.stderr or render.stdout)}")

    images = {}
    for index, image_path in enumerate(image_paths, 1):
        with open(image_path, "rb") as image_file:
            images[index] = "data:image/png;base64," + base64.b64encode(image_file.read()).decode("ascii")
    return images


def extract_slides(content: bytes, presentation_id: str) -> list[dict]:
    """Extract slide text and render the original uploaded slide artwork."""
    slide_image_b64 = {}
    temp_dir = tempfile.mkdtemp(prefix="slidevoxa_")
    temp_pptx = os.path.join(temp_dir, "temp_pres.pptx")
    with open(temp_pptx, "wb") as pptx_file:
        pptx_file.write(content)

    prs = Presentation(io.BytesIO(content))
    print(f"[extract] Rendering {len(prs.slides)} slides for {safe_str(presentation_id)}")

    if os.name == "nt":
        powerpoint = None
        presentation = None
        pythoncom = None
        try:
            import win32com.client
            import pythoncom as com_runtime
            pythoncom = com_runtime
            pythoncom.CoInitialize()
            powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
            powerpoint.Visible = False
            presentation = powerpoint.Presentations.Open(os.path.abspath(temp_pptx), ReadOnly=1, WithWindow=False)
            width = 1600
            height = int(width * presentation.PageSetup.SlideHeight / presentation.PageSetup.SlideWidth)
            for index, slide in enumerate(presentation.Slides, 1):
                image_path = os.path.join(temp_dir, f"slide-{index}.png")
                slide.Export(image_path, "PNG", width, height)
                if os.path.isfile(image_path):
                    with open(image_path, "rb") as image_file:
                        slide_image_b64[index] = "data:image/png;base64," + base64.b64encode(image_file.read()).decode("ascii")
        except Exception as error:
            print(f"[extract] PowerPoint rendering failed: {safe_str(error)}")
        finally:
            try:
                if presentation is not None:
                    presentation.Close()
            except Exception:
                pass
            try:
                if powerpoint is not None:
                    powerpoint.Quit()
            except Exception:
                pass
            try:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
            except Exception:
                pass

    if len(slide_image_b64) < len(prs.slides):
        try:
            slide_image_b64 = _render_pptx_with_libreoffice(temp_pptx, temp_dir, len(prs.slides))
            print(f"[extract] LibreOffice rendered {len(slide_image_b64)} original slides")
        except Exception as error:
            print(f"[extract] Cross-platform rendering failed: {safe_str(error)}")

    slides_data = []
    for index, slide in enumerate(prs.slides, 1):
        title = ""
        points = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if getattr(shape, "is_placeholder", False) and shape.placeholder_format.idx in (0, 1):
                title = text
            else:
                points.append(text)
        slides_data.append({
            "slide_number": index,
            "title": title or f"Slide {index}",
            "points": list(dict.fromkeys(points)),
            "image_data_uri": slide_image_b64.get(index),
        })

    shutil.rmtree(temp_dir, ignore_errors=True)
    return slides_data


# Language display names used in prompts
_LANG_NAMES = {
    "en-IN": "English",
    "te-IN": "Telugu",
    "ta-IN": "Tamil",
    "hi-IN": "Hindi",
}

VALID_SARVAM_SPEAKERS = {
    "shubh", "ratan", "dev", "roopa", "kavya", "priya", "simran", "mani",
    "anushka", "rahul", "pooja", "rohan", "gokul", "vijay", "shruti", "suhani",
    "mohit", "kavitha", "rehan", "soham", "rupali", "hitesh", "aditya", "ritu",
    "neha", "amit", "ishita", "shreya", "varun", "manan", "sumit", "kabir",
    "aayan", "ashutosh", "advait", "anand", "tanya", "tarun", "sunny", "karun",
    "abhilash", "manisha", "vidya", "arya"
}

_SARVAM_DEFAULT_SPEAKERS = {
    "en-IN": "shubh",
    "te-IN": "shubh",
    "ta-IN": "mani",
    "hi-IN": "shubh",
}

import re

def clean_sarvam_response(msg: dict, language: str = "en-IN") -> str:
    """Extract clean script/answer from Sarvam AI model response, handling reasoning blocks."""
    if not msg:
        return ""
    content = msg.get("content")
    reasoning = msg.get("reasoning_content")
    text = content if content else (reasoning or "")

    # Strip <think>...</think>
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Match native language character ranges for Indian languages
    ranges = {
        "te-IN": r'[\u0C00-\u0C7F]',  # Telugu
        "ta-IN": r'[\u0B80-\u0BFF]',  # Tamil
        "hi-IN": r'[\u0900-\u097F]',  # Hindi / Devanagari
    }

    pattern = ranges.get(language)
    if pattern:
        lines = [line.strip() for line in text.split("\n") if re.search(pattern, line)]
        clean_lines = []
        for l in lines:
            # Clean list formatting and quotes
            l = re.sub(r'^[0-9\.\-\*\s"\'`]+', '', l).strip().strip('"\'`')
            # Remove trailing English translation comments e.g. (Let's discuss...)
            l = re.sub(r'\s*\([A-Za-z0-9\s\.,\'-]+\)\s*$', '', l).strip()
            if l and not l.startswith("Option") and not l.startswith("Sentence"):
                clean_lines.append(l)
        if clean_lines:
            # Return distinct clean lines
            return " ".join(dict.fromkeys(clean_lines))

    # Fallback for English or unpatterned text: get last non-empty block
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if paragraphs:
        last = paragraphs[-1]
        return re.sub(r'^[0-9\.\-\*\s"\'`]+', '', last).strip().strip('"\'`')
    return text.strip()


async def async_generate_script_sarvam(slide: dict, session: aiohttp.ClientSession, language: str = "en-IN") -> str:
    """Generate a natural speaking script for a slide using Sarvam AI asynchronously."""
    title = slide.get("title", "")
    points = slide.get("points", [])
    body = slide.get("body", "")

    bullet_text = "\n".join(f"- {p}" for p in points) if points else ""
    content = f"Title: {title}\n{bullet_text}\n{body}".strip()

    lang_name = _LANG_NAMES.get(language, "English")
    if language == "en-IN":
        lang_instruction = (
            "You are a professional AI presenter. Convert the slide content "
            "into a natural 2-3 sentence spoken presentation script in English. "
            "Output ONLY the spoken script in plain text. Do not output reasoning or explanations."
        )
    else:
        lang_instruction = (
            f"You are a professional AI presenter. Convert the slide content "
            f"into a natural 2-3 sentence spoken presentation script in {lang_name}. "
            f"The entire script MUST be written in {lang_name} language only. "
            f"Output ONLY the {lang_name} spoken script in plain text. Do not output reasoning or English text."
        )

    prompt = f"{lang_instruction}\n\nSlide content:\n{content}\n\nScript:"

    try:
        async with session.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sarvam-30b",
                "messages": [
                    {"role": "system", "content": f"You are a professional presenter. Output ONLY the raw spoken script in {lang_name}. No explanations."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
            },
            timeout=30,
        ) as response:
            if response.status == 200:
                data = await response.json()
                msg = data["choices"][0]["message"]
                script = clean_sarvam_response(msg, language=language)
                if script:
                    return script
            else:
                text = await response.text()
                print(f"[Sarvam script] Error {response.status}: {safe_str(text[:200])}")
    except Exception as e:
        print(f"[Sarvam script] Exception: {safe_str(e)}")

    # Fallback: build a basic script from slide content
    script = f"In this slide, we discuss {title}."
    if points:
        script += " The key points covered are: " + "; ".join(points[:4]) + "."
    if body:
        script += " " + body[:200]
    return script


async def async_generate_audio_for_slide(script: str, slide_number: int, presentation_id: str, voice_id: str, session: aiohttp.ClientSession, language: str = "en-IN") -> str | None:
    """
    Generate audio for a slide asynchronously.
    - For non-English languages: always use Sarvam TTS (ElevenLabs doesn't support Indian languages).
    - For English: tries ElevenLabs first (if voice_id is an ElevenLabs ID), falls back to Sarvam.
    Returns a base64-encoded audio string (data URI) or None.
    """
    # For non-English, skip ElevenLabs and go directly to Sarvam TTS
    if language != "en-IN":
        print(f"[Audio] Non-English language ({language}), using Sarvam TTS for slide_{slide_number} (speaker={voice_id})")
        return await async_generate_audio_sarvam_b64(script, slide_number, session, language=language, speaker=voice_id)

    # Try ElevenLabs first if key is available and voice_id is an ElevenLabs ID
    if ELEVENLABS_API_KEY and voice_id not in VALID_SARVAM_SPEAKERS:
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            async with session.post(
                url,
                json={
                    "text": script,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.4,
                        "similarity_boost": 0.8,
                        "style": 0.0,
                        "use_speaker_boost": True,
                    },
                },
                headers={
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": ELEVENLABS_API_KEY,
                },
                timeout=60,
            ) as response:
                if response.status == 200:
                    content = await response.read()
                    audio_b64 = base64.b64encode(content).decode("utf-8")
                    print(f"[ElevenLabs] slide_{slide_number} ok ({len(content)} bytes)")
                    return f"data:audio/mpeg;base64,{audio_b64}"
                else:
                    text = await response.text()
                    print(f"[ElevenLabs] Error {response.status}: {safe_str(text[:200])} - falling back")
        except Exception as e:
            print(f"[ElevenLabs] Exception: {safe_str(e)} - falling back")

    # Sarvam TTS fallback
    return await async_generate_audio_sarvam_b64(script, slide_number, session, language=language, speaker=voice_id)


async def async_generate_audio_sarvam_b64(script: str, slide_number: int, session: aiohttp.ClientSession, language: str = "en-IN", speaker: str = None) -> str | None:
    """Sarvam AI TTS called asynchronously. Returns a base64 data URI string or None."""
    if not SARVAM_API_KEY:
        print("[Sarvam TTS] No API key -- skipping audio")
        return None

    if not speaker or speaker not in VALID_SARVAM_SPEAKERS:
        speaker = _SARVAM_DEFAULT_SPEAKERS.get(language, "shubh")

    clean_text = script.strip()[:2000]

    try:
        async with session.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={
                "api-subscription-key": SARVAM_API_KEY,
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": [clean_text],
                "target_language_code": language,
                "speaker": speaker,
                "pace": 1.0,
                "speech_sample_rate": 22050,
                "enable_preprocessing": True,
                "model": "bulbul:v3",
            },
            timeout=60,
        ) as response:
            if response.status == 200:
                data = await response.json()
                audio_b64 = data.get("audios", [None])[0]
                if audio_b64:
                    print(f"[Sarvam TTS] slide_{slide_number} ok ({language}, speaker={speaker}, {len(audio_b64)} b64 chars)")
                    return f"data:audio/wav;base64,{audio_b64}"
            else:
                text = await response.text()
                print(f"[Sarvam TTS] Error {response.status}: {safe_str(text[:300])}")
    except Exception as e:
        print(f"[Sarvam TTS] Exception: {safe_str(e)}")

    return None


async def async_answer_question(question: str, slides_context: list[dict], language: str, session: aiohttp.ClientSession, voice_id: str = None) -> tuple[str, str | None]:
    """
    Generate an AI answer to a listener's question using the presentation context.
    Returns (answer_text, audio_data_uri_or_None).
    """
    lang_name = _LANG_NAMES.get(language, "English")

    # Keep slide titles, extracted text, and generated narration in the answer context.
    ctx_parts = []
    context_size = 0
    for slide in slides_context:
        title = str(slide.get("title", ""))[:240]
        points = slide.get("points", []) or []
        if not isinstance(points, list):
            points = [points]
        point_text = "; ".join(str(point)[:320] for point in points[:8] if point)
        script = str(slide.get("script", ""))[:700]
        section = f"Slide {slide.get('slide_number', '?')}: {title}"
        if point_text:
            section += f"\nExtracted slide content: {point_text}"
        if script:
            section += f"\nNarration: {script}"
        if context_size + len(section) > 28000:
            break
        ctx_parts.append(section)
        context_size += len(section)
    context_str = "\n\n".join(ctx_parts)

    if language == "en-IN":
        lang_instr = "Answer in English."
    else:
        lang_instr = f"You MUST answer entirely in {lang_name} language only."

    prompt = (
        f"You are the presenter answering questions about the uploaded slide deck. "
        f"Answer only from the presentation context below. Do not invent facts or add outside claims. "
        f"If the slides do not contain the answer, say that the presentation does not specify it. "
        f"{lang_instr}\n\n"
        f"Presentation context:\n{context_str}\n\n"
        f"Listener's question: {question}\n\n"
        f"Give a clear, helpful answer in 2-4 sentences as the presenter. "
        f"Output ONLY the spoken answer text in {lang_name}."
    )

    answer_text = ""
    try:
        async with session.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sarvam-30b",
                "messages": [
                    {"role": "system", "content": f"Output ONLY the answer in {lang_name}. No reasoning or explanations."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
            },
            timeout=40,
        ) as response:
            if response.status == 200:
                data = await response.json()
                msg = data["choices"][0]["message"]
                answer_text = clean_sarvam_response(msg, language=language)
            else:
                text = await response.text()
                print(f"[Sarvam Q&A] Error {response.status}: {safe_str(text[:200])}")
    except Exception as e:
        print(f"[Sarvam Q&A] Exception: {safe_str(e)}")

    if not answer_text:
        answer_text = "I couldn’t generate a deck-based answer just now. Please try your question again."

    # Generate TTS audio for the answer
    audio_uri = await async_generate_audio_sarvam_b64(answer_text, 0, session, language=language, speaker=voice_id)

    return answer_text, audio_uri


async def async_generate_audience_questions(slides_data: list[dict], session: aiohttp.ClientSession, language: str = "en-IN") -> list[str]:
    """Generate possible audience questions using Sarvam AI asynchronously."""
    summary_parts = []
    for slide in slides_data:
        summary_parts.append(f"Slide {slide['slide_number']}: {slide.get('title', '')}")
        pts = slide.get("points", [])
        if pts:
            summary_parts.append("  Points: " + ", ".join(pts[:3]))

    presentation_summary = "\n".join(summary_parts)

    lang_name = _LANG_NAMES.get(language, "English")
    if language == "en-IN":
        lang_instr = "Generate the questions in English."
    else:
        lang_instr = f"Generate the questions in {lang_name} language only."

    prompt = (
        f"You are an expert audience member. Based on this presentation, generate 5 insightful "
        f"questions that an audience member might ask. {lang_instr} "
        f"Format as a numbered list (1. Question, 2. Question, etc.). Be specific and thought-provoking.\n\n"
        f"Presentation:\n{presentation_summary}\n\nQuestions:"
    )

    try:
        async with session.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sarvam-30b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            },
            timeout=30,
        ) as response:
            if response.status == 200:
                data = await response.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content") or msg.get("reasoning_content") or ""
                import re
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                questions = []
                for line in content.split("\n"):
                    line = line.strip()
                    if line and (line[0].isdigit() or line.startswith("-")):
                        q = line.lstrip("0123456789.-) ").strip()
                        if q:
                            questions.append(q)
                if questions:
                    return questions[:7]
            else:
                text = await response.text()
                print(f"[Sarvam Q&A] Error {response.status}: {safe_str(text[:200])}")
    except Exception as e:
        print(f"[Sarvam Q&A] Exception: {safe_str(e)}")

    # Fallback questions
    topic = slides_data[0]["title"] if slides_data else "this topic"
    return [
        f"What are the key challenges in implementing {topic}?",
        "How does this compare to existing approaches in the field?",
        "What is the future direction of this work?",
        "Can you elaborate on the most surprising finding?",
        "What would be the next steps after this presentation?",
    ]
