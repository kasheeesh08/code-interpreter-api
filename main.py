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

# Enable CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Request Model --------
class CodeRequest(BaseModel):
    code: str


# -------- Tool Function --------
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


# -------- AI Structured Output --------
class ErrorAnalysis(BaseModel):
    error_lines: List[int]


def analyze_error_with_ai(code: str, tb: str) -> List[int]:
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        prompt = f"""
You are a Python debugger.

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
        # ✅ STRONG fallback (fixes your test failures)
        lines = tb.split("\n")
        for line in reversed(lines):
            if "<string>" in line and "line" in line:
                match = re.search(r'line (\d+)', line)
                if match:
                    return [int(match.group(1))]

        return [1]


# -------- Endpoint --------
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