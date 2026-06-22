import json
import os
import subprocess
from typing import Optional

import anthropic

import json as _json
import pathlib as _pathlib

def _load_taxonomy() -> str:
    p = _pathlib.Path(__file__).parent / "taxonomy.json"
    data = _json.loads(p.read_text())
    lines = []
    for d in data["domains"]:
        subs = " · ".join(d["subdomains"])
        lines.append(f'{d["name"]} — {d["description"]}\n    Subdomains: {subs}')
    return "\n".join(lines)

_TAXONOMY = _load_taxonomy()

SYSTEM = f"""\
You are a streaming-platform architect classifying repositories from a 15-year-old TV-as-a-Service platform.
Assign each repo to exactly one domain AND one subdomain from the fixed taxonomy below.

{_TAXONOMY}

Reply ONLY with valid JSON — no markdown fences, no extra text:
{{
  "domain":       "<domain name exactly as listed — include the number>",
  "subdomain":    "<subdomain name exactly as listed for that domain>",
  "capability":   "<specific capability within the subdomain, e.g. 'HLS packaging pipeline', 'OAuth2 token service'>",
  "confidence":   "high|medium|low",
  "summary":      "<what this repo does in ≤3 sentences, citing the files that support it>",
  "flags":        ["split-candidate|duplicate|orphan|dormant — include only if truly applicable"],
  "split_domains":["<if split-candidate: the other domains, by number>"],
  "evidence":     ["<file paths seen that justify the domain assignment>"]
}}

Rules:
- subdomain MUST be chosen from the listed subdomains for the assigned domain — do not invent new ones.
- Cite only files present in the provided content.
- If nothing is readable, set confidence=low and flag orphan.
- split-candidate means the repo meaningfully spans 2+ domains, not merely imports infra libs.
"""


def _gcloud(key: str) -> str:
    try:
        r = subprocess.run(["gcloud", "config", "get-value", key],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _build_client() -> tuple[anthropic.Anthropic | anthropic.AnthropicVertex, str]:
    """
    Auto-detect backend:
      Vertex  → GOOGLE_CLOUD_PROJECT set, or resolved from gcloud CLI (uses ADC)
      Direct  → ANTHROPIC_API_KEY set
    Model comes from ANTHROPIC_MODEL or a backend-appropriate default.
    """
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or _gcloud("project")
    )
    if project:
        raw_region = (
            os.environ.get("ANTHROPIC_VERTEX_REGION")
            or _gcloud("compute/region")
        )
        # gcloud returns "europe/west1", Vertex wants "europe-west1"
        region = raw_region.replace("/", "-") if raw_region else "us-east5"
        client = anthropic.AnthropicVertex(project_id=project, region=region)
        model  = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku@20240307")
        return client, model

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
        model  = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        return client, model

    raise RuntimeError(
        "No Anthropic credentials found.\n"
        "  Vertex : set GOOGLE_CLOUD_PROJECT (uses ADC)\n"
        "  Direct : set ANTHROPIC_API_KEY"
    )


class Classifier:
    def __init__(self):
        self.client, self.model = _build_client()

    def classify(
        self,
        repo_name: str,
        language: Optional[str],
        files: dict[str, str],
    ) -> dict:
        file_text = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in files.items()
        )
        user_msg = (
            f"Repository: {repo_name}\n"
            f"Primary language: {language or 'unknown'}\n\n"
            + (file_text or "(no files readable — classify from name only, confidence=low)")
        )

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM,
            messages=[
                {"role": "user",      "content": user_msg},
                {"role": "assistant", "content": "{"},   # prefill forces JSON start
            ],
        )

        # Model continues from the prefilled "{" — prepend it back
        text = "{" + resp.content[0].text

        # Extract the first complete JSON object (ignore any trailing text)
        depth, end = 0, 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        return json.loads(text[:end] if end else text)
