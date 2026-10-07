"""Morning Briefing Agent: Gmail + Google Calendar + Slack, summarized by an LLM via OpenRouter."""

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from slack_sdk import WebClient
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

# ---------------------------------------------------------------------------
# Credentials / config (loaded from .env; never printed)
# ---------------------------------------------------------------------------

load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]

CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"

# Read-only scopes: this agent only ever reads Gmail/Calendar, never modifies them.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_google_credentials() -> Credentials:
    """Load, refresh, or create Google OAuth credentials for Gmail/Calendar (read-only).

    Uses credentials.json for the OAuth client, caches the resulting token in
    token.json, and refreshes it automatically when it has expired.
    """
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def check_gmail(hours_back: int = 12) -> list[dict]:
    """Fetch unread Gmail messages from the last `hours_back` hours.

    Returns a list of dicts: sender, subject, date, and a snippet (<=200 chars).
    """
    creds = get_google_credentials()
    service = build("gmail", "v1", credentials=creds)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    query = f"is:unread after:{int(cutoff.timestamp())}"

    response = service.users().messages().list(userId="me", q=query).execute()
    message_refs = response.get("messages", [])

    emails = []
    for ref in message_refs:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        # Noise filtering: skip emails Gmail itself has already classified as
        # promotional/marketing (its own "Promotions" tab signal), e.g. SHEIN-style
        # blasts. This is conservative because Gmail's classifier does not apply this
        # label to work, school, security, event, mentor, or personal email.
        if "CATEGORY_PROMOTIONS" in msg.get("labelIds", []):
            continue

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        emails.append(
            {
                "sender": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", "")[:200],
            }
        )

    return emails


@tool
def check_calendar(hours_ahead: int = 24) -> list[dict]:
    """Fetch calendar events over the next `hours_ahead` hours.

    Returns a list of dicts: title, start, end, location, and attendees.
    """
    creds = get_google_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(hours=hours_ahead)).isoformat()

    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for event in response.get("items", []):
        start = event.get("start", {})
        end = event.get("end", {})
        attendees = [a.get("email") for a in event.get("attendees", []) if a.get("email")]
        events.append(
            {
                "title": event.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date")),
                "end": end.get("dateTime", end.get("date")),
                "location": event.get("location", ""),
                "attendees": attendees,
            }
        )

    return events


@tool
def check_slack(hours_back: int = 12, max_channels: int = 5) -> list[dict]:
    """Read recent messages from the top `max_channels` most active Slack channels.

    Returns a list of dicts: channel name and up to 5 recent messages per channel.
    """
    client = WebClient(token=SLACK_BOT_TOKEN)

    channels_response = client.conversations_list(
        types="public_channel,private_channel",
        exclude_archived=True,
        limit=200,
    )
    member_channels = [c for c in channels_response.get("channels", []) if c.get("is_member")]

    def _latest_ts(channel: dict) -> float:
        latest = channel.get("latest") or {}
        try:
            return float(latest.get("ts", 0))
        except (TypeError, ValueError):
            return 0.0

    # "Most active" = most recent message activity.
    member_channels.sort(key=_latest_ts, reverse=True)
    active_channels = member_channels[:max_channels]

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp()

    results = []
    for channel in active_channels:
        history = client.conversations_history(
            channel=channel["id"],
            oldest=f"{cutoff_ts:.6f}",
            limit=5,
        )
        messages = [m.get("text", "") for m in history.get("messages", [])[:5]]
        results.append({"channel": channel.get("name", channel["id"]), "messages": messages})

    return results


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a Morning Briefing Agent.

On every request, you MUST call all three tools, in this exact order, before replying:
1. check_gmail
2. check_calendar
3. check_slack

After gathering their results, synthesize everything into a reply with exactly these five
section headers, in this order, each followed by a short bulleted summary (or "Nothing to
report." if a section is empty):

URGENT
UPCOMING EVENTS
SLACK HIGHLIGHTS
OTHER EMAILS
SUGGESTED ACTIONS

For the URGENT section, explicitly flag any item (from Gmail, Calendar, or Slack) that shows
signs of urgency, including:
- Senders or messages related to important people or security matters
- Subject lines or messages containing urgent or time-sensitive language (e.g. "urgent",
  "asap", "action required", "deadline", "today", "immediately")
- Account, login, or security alerts (e.g. password resets, suspicious activity, verification
  codes)
- Meetings or events starting soon or requiring immediate action or preparation
- Messages that clearly expect a reply or decision soon
Place only matching items in URGENT, and exclude them from OTHER EMAILS so nothing is
duplicated across sections.

Do not invent information that did not come from the tool results.
""".strip()

model = LiteLLMModel(
    client_args={
        "api_key": OPENROUTER_API_KEY,
        "base_url": "https://openrouter.ai/api/v1",
    },
    model_id="openrouter/openrouter/free",
    params={"max_tokens": 4096},
)

agent = Agent(
    model=model,
    tools=[check_gmail, check_calendar, check_slack],
    system_prompt=SYSTEM_PROMPT,
    callback_handler=None,
)


def run():
    result = agent("What did I miss? Give me my morning briefing.")
    print(result)


if __name__ == "__main__":
    run()
