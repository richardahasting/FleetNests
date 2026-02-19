"""
AI-routed member feedback for Bentley Boat Club.

process_feedback(user, text, image_bytes, image_content_type) -> (bool, str)

Routes via the `claude` CLI (no ANTHROPIC_API_KEY needed in the app):
- Bugs / feature requests  → GitHub issue
- Everything else          → email to FEEDBACK_EMAIL
- claude CLI not found     → fallback plain email, no crash
- Any error                → fallback plain email, no crash
"""

import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/gif":  ".gif",
    "image/webp": ".webp",
}

_PROMPT = """\
You are the feedback assistant for Bentley Boat Club, a private boating club.
A logged-in member has submitted feedback through the app. Triage it and decide
where to route it.

Rules:
- Route to github_issue for: bugs, broken features, UI glitches, error messages,
  performance problems, or feature requests / suggestions to improve the app.
- Route to email for: general comments, questions, praise, thanks, concerns about
  club policy, or anything that is not a software bug or feature request.
- Be concise but include all relevant context in the title/body.
- Always attribute the feedback to the member by name in the body.
- If a screenshot is referenced, note what it shows.

Output ONLY a single JSON object — no other text, no markdown fences.

For bugs / feature requests:
{"action":"github_issue","title":"<short title>","body":"<full body>","labels":["bug"|"enhancement"]}

For everything else:
{"action":"email","subject":"<subject>","body":"<full body>"}
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_feedback(
    user: dict,
    text: str,
    image_bytes: bytes | None,
    image_content_type: str | None,
) -> tuple[bool, str]:
    """Triage and route member feedback via the claude CLI.

    Returns (success, action) where action is one of:
      "github_issue", "email", "fallback_email"
    """
    try:
        result = _call_claude_cli(user, text, image_bytes, image_content_type)
    except Exception as exc:
        log.error("claude CLI error in process_feedback: %s", exc)
        return _fallback_email(user, text)

    action = result.get("action")

    if action == "github_issue":
        ok = _create_github_issue(result["title"], result["body"], result.get("labels", []))
        if ok:
            return True, "github_issue"
        log.warning("GitHub issue creation failed; falling back to email for: %s", result["title"])
        ok = _send_email(f"[Feature/Bug] {result['title']}", result["body"])
        return ok, "fallback_email"

    if action == "email":
        ok = _send_email(result["subject"], result["body"])
        return ok, "email"

    log.warning("Unexpected action from claude CLI: %s; falling back to email", action)
    return _fallback_email(user, text)


# ---------------------------------------------------------------------------
# claude CLI call
# ---------------------------------------------------------------------------

def _call_claude_cli(
    user: dict,
    text: str,
    image_bytes: bytes | None,
    image_content_type: str | None,
) -> dict:
    """Invoke the claude CLI and return parsed JSON routing decision."""
    image_path = None
    try:
        # Write image to a temp file so claude can read it
        if image_bytes and image_content_type in ALLOWED_IMAGE_TYPES:
            ext = _IMAGE_EXTENSIONS.get(image_content_type, ".jpg")
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(image_bytes)
                image_path = f.name

        message = (
            f"Member: {user['full_name']} ({user.get('email', 'unknown')})\n\n"
            f"Feedback:\n{text}"
        )
        if image_path:
            message += f"\n\nScreenshot: {image_path}"

        claude_bin = os.environ.get("CLAUDE_BIN", "/home/richard/.local/bin/claude")
        # Remove CLAUDECODE so nested-session detection doesn't block us
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        result = subprocess.run(
            [claude_bin, "-p", _PROMPT],
            input=message,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()}")

        output = result.stdout.strip()
        # Strip any accidental markdown fences
        if output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
        return json.loads(output)

    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


# ---------------------------------------------------------------------------
# GitHub issue creation (stdlib urllib only)
# ---------------------------------------------------------------------------

def _create_github_issue(title: str, body: str, labels: list) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPO", "richardahasting/bentley-boat")
    if not token:
        log.error("GITHUB_TOKEN not set; cannot create GitHub issue: %s", title)
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
            return resp.status in (200, 201)
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


def _fallback_email(user: dict, text: str) -> tuple[bool, str]:
    """Send a plain email when the claude CLI is unavailable."""
    subject = f"Member Feedback from {user['full_name']}"
    body = (
        f"Feedback submitted by {user['full_name']} ({user.get('email', 'unknown')})\n\n"
        f"{text}"
    )
    ok = _send_email(subject, body)
    return ok, "fallback_email"
