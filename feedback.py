"""
AI-routed member feedback for Bentley Boat Club.

process_feedback(user, text, image_bytes, image_content_type) -> (bool, str)

Routes via Claude Haiku:
- Bugs / feature requests  → GitHub issue (create_github_issue tool)
- Everything else          → email to FEEDBACK_EMAIL (send_email tool)
- No ANTHROPIC_API_KEY     → fallback plain email, no crash
- Claude error             → fallback plain email, no crash
- No GITHUB_TOKEN          → returns (False, "github_issue") — 500 to client
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_SYSTEM_PROMPT = """\
You are the feedback assistant for Bentley Boat Club, a private boating club.
A logged-in member has submitted feedback through the app. Your job is to triage
it and route it to the right place by calling exactly one tool.

Rules:
- Call create_github_issue for: bugs, broken features, UI glitches, error messages,
  performance problems, or feature requests / suggestions to improve the app.
- Call send_email for: general comments, questions, praise, "thanks", concerns about
  club policy, or anything that is not a software bug or feature request.
- Be concise but include all relevant context in the issue/email body.
- If a screenshot is attached, describe what it shows and include that in the body.
- Always attribute the feedback to the member by name in the body.
- Do not invent details not present in the feedback.
- Respond ONLY with a tool call — no explanatory text.\
"""

_TOOLS = [
    {
        "name": "create_github_issue",
        "description": (
            "File a GitHub issue for bugs, broken features, UI glitches, "
            "error messages, performance problems, or feature requests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short descriptive title for the issue",
                },
                "body": {
                    "type": "string",
                    "description": "Full issue body with details and member attribution",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to apply: 'bug' or 'enhancement'",
                },
            },
            "required": ["title", "body", "labels"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send an email for general feedback, questions, praise, "
            "or non-technical concerns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Email subject"},
                "body": {
                    "type": "string",
                    "description": "Email body with feedback and member attribution",
                },
            },
            "required": ["subject", "body"],
        },
    },
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_feedback(
    user: dict,
    text: str,
    image_bytes: bytes | None,
    image_content_type: str | None,
) -> tuple[bool, str]:
    """Triage and route member feedback via Claude Haiku.

    Returns (success, action) where action is one of:
      "github_issue", "email", "fallback_email"
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set; using fallback email for feedback")
        return _fallback_email(user, text, image_bytes)

    try:
        tool_use = _call_claude(api_key, user, text, image_bytes, image_content_type)
    except Exception as exc:
        log.error("Claude API error in process_feedback: %s", exc)
        return _fallback_email(user, text, image_bytes)

    tool_name = tool_use["name"]
    inp = tool_use["input"]

    if tool_name == "create_github_issue":
        ok = _create_github_issue(inp["title"], inp["body"], inp.get("labels", []))
        return ok, "github_issue"

    if tool_name == "send_email":
        ok = _send_email(inp["subject"], inp["body"])
        return ok, "email"

    log.warning("Unexpected tool name from Claude: %s; falling back to email", tool_name)
    return _fallback_email(user, text, image_bytes)


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def _call_claude(
    api_key: str,
    user: dict,
    text: str,
    image_bytes: bytes | None,
    image_content_type: str | None,
) -> dict:
    """Call Claude Haiku with tool_choice=any; return the tool_use block as a dict."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)

    content: list = []
    if image_bytes and image_content_type in ALLOWED_IMAGE_TYPES:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_content_type,
                "data": base64.b64encode(image_bytes).decode(),
            },
        })

    content.append({
        "type": "text",
        "text": (
            f"Member: {user['full_name']} ({user.get('email', 'unknown')})\n\n"
            f"Feedback:\n{text}"
        ),
    })

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=_TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": content}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return {"name": block.name, "input": block.input}

    raise ValueError("Claude returned no tool_use block despite tool_choice=any")


# ---------------------------------------------------------------------------
# GitHub issue creation (stdlib urllib only)
# ---------------------------------------------------------------------------

def _create_github_issue(title: str, body: str, labels: list) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPO", "hastingtx/bentley-boat")
    if not token:
        log.error("GITHUB_TOKEN not set; cannot create GitHub issue titled: %s", title)
        return False

    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode()
    url = f"https://api.github.com/repos/{repo}/issues"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization":        f"Bearer {token}",
            "Accept":               "application/vnd.github+json",
            "Content-Type":         "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                return True
            log.error("GitHub API returned unexpected status %s", resp.status)
            return False
    except urllib.error.HTTPError as exc:
        log.error("GitHub API HTTP %s: %s", exc.code, exc.read())
        return False
    except Exception as exc:
        log.error("GitHub API error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Email sending (delegates to email_notify)
# ---------------------------------------------------------------------------

def _send_email(subject: str, body: str) -> bool:
    import email_notify
    to_addr = os.environ.get("FEEDBACK_EMAIL", "")
    return email_notify.send_email(to_addr, subject, body)


def _fallback_email(
    user: dict, text: str, image_bytes: bytes | None
) -> tuple[bool, str]:
    """Send a plain email when Claude is unavailable."""
    subject = f"Member Feedback from {user['full_name']}"
    body = (
        f"Feedback submitted by {user['full_name']} ({user.get('email', 'unknown')})\n\n"
        f"{text}"
    )
    if image_bytes:
        body += "\n\n[A screenshot was attached but could not be processed — Claude unavailable]"

    ok = _send_email(subject, body)
    return ok, "fallback_email"
