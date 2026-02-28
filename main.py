from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os
import re
import time
import yt_dlp

from dotenv import load_dotenv
from google import genai

load_dotenv()

app = FastAPI()

# -------- CORS --------
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- MODELS --------
class CodeRequest(BaseModel):
    code: str

class AskRequest(BaseModel):
    video_url: str
    topic: str


# -------- CODE INTERPRETER --------
def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


class ErrorAnalysis(BaseModel):
    error_lines: List[int]


def analyze_error_with_ai(code: str, tb: str) -> List[int]:
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        prompt = f"""
Return ONLY the exact line number where the error occurred.

Rules:
- Line numbers start from 1
- Return ONLY ONE line number
- Output STRICT JSON: {{"error_lines": [number]}}

CODE:
{code}

TRACEBACK:
{tb}
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

        result = ErrorAnalysis.model_validate_json(response.text)
        return result.error_lines

    except Exception:
        lines = tb.split("\n")
        for line in reversed(lines):
            if "<string>" in line and "line" in line:
                match = re.search(r'line (\d+)', line)
                if match:
                    return [int(match.group(1))]
        return [1]


@app.post("/code-interpreter")
def code_interpreter(req: CodeRequest):
    execution = execute_python_code(req.code)

    if execution["success"]:
        return {
            "error": [],
            "result": execution["output"]
        }

    error_lines = analyze_error_with_ai(req.code, execution["output"])

    return {
        "error": error_lines,
        "result": execution["output"]
    }


# -------- ASK ENDPOINT --------
@app.post("/ask")
def ask(req: AskRequest):
    video_url = req.video_url
    topic = req.topic

    filename = "audio.%(ext)s"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': filename,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    audio_file = "audio.mp3"

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    uploaded = client.files.upload(file=audio_file)

    while True:
        file_state = client.files.get(name=uploaded.name)
        if file_state.state == "ACTIVE":
            break
        time.sleep(2)

    prompt = f"""
Find the FIRST timestamp where this topic is spoken.

Topic: "{topic}"

Rules:
- Return ONLY timestamp
- Format MUST be HH:MM:SS
- No explanation
"""

    response = client.models.generate_content(
        model="gemini-1.5-pro",
        contents=[uploaded, prompt]
    )

    timestamp = response.text.strip()

    if os.path.exists(audio_file):
        os.remove(audio_file)

    return {
        "timestamp": timestamp,
        "video_url": video_url,
        "topic": topic
    }