from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os
import re

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
Return ONLY the line number where the Python error occurred.

Rules:
- Only ONE number
- JSON format: {{"error_lines": [number]}}

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


# -------- FINAL /ask (NO yt-dlp) --------
@app.post("/ask")
def ask(req: AskRequest):
    video_url = req.video_url
    topic = req.topic

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    prompt = f"""
You are given a YouTube video.

Find the FIRST timestamp where this topic is spoken.

Topic: "{topic}"

Rules:
- Return ONLY timestamp
- Format MUST be HH:MM:SS
- No explanation

Video URL:
{video_url}
"""

    response = client.models.generate_content(
        model="gemini-1.5-pro",
        contents=prompt
    )

    return {
        "timestamp": response.text.strip(),
        "video_url": video_url,
        "topic": topic
    }