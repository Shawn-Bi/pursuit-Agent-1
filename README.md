# Morning Briefing Agent

An AI agent that checks your Gmail, Google Calendar, and Slack each morning and synthesizes
everything into a single, structured briefing — so you know what you missed without opening
three different apps.

## What it does

On request, the agent gathers:
- Unread Gmail from the last N hours (with basic marketing/promo noise filtered out)
- Upcoming Google Calendar events for the next N hours
- Recent messages from your most active Slack channels

It then uses an LLM to synthesize all of that into a short, organized morning briefing with
explicit urgency detection — flagging time-sensitive items (security alerts, deadlines,
imminent meetings, messages awaiting a reply) separately from routine updates.

## Agent workflow

```
Gmail → Google Calendar → Slack → LLM synthesis → Morning Briefing
```

The agent always gathers data from all three sources, in that order, before asking the LLM
to produce the final briefing.

## Tools

| Tool | Purpose |
|---|---|
| `check_gmail` | Fetches unread emails from the last N hours (sender, subject, date, snippet) |
| `check_calendar` | Fetches upcoming events for the next N hours (title, start/end, location, attendees) |
| `check_slack` | Fetches recent messages from the top active Slack channels |

## Tech stack

- Python
- [Strands Agents](https://github.com/strands-agents/sdk-python)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [OpenRouter](https://openrouter.ai/)
- Gmail API
- Google Calendar API
- Slack API

## The agent loop

1. **Receive goal** — the agent is asked for a morning briefing.
2. **Choose/call tools** — it calls `check_gmail`, `check_calendar`, and `check_slack` in
   order to gather fresh data.
3. **Observe results** — each tool's output (emails, events, messages) is returned to the
   agent as context.
4. **Synthesize final briefing** — the LLM combines all three results into a single
   response organized into fixed sections (URGENT, UPCOMING EVENTS, SLACK HIGHLIGHTS,
   OTHER EMAILS, SUGGESTED ACTIONS).

## Setup

### 1. Install dependencies

```bash
pip install strands-agents python-dotenv litellm \
    google-auth google-auth-oauthlib google-api-python-client slack_sdk
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your-openrouter-api-key
SLACK_BOT_TOKEN=your-slack-bot-token
```

### 3. Configure Google OAuth

1. Create an OAuth client (Desktop app) in the Google Cloud Console with the Gmail and
   Google Calendar APIs enabled.
2. Download the client secret and save it as `credentials.json` in the project root.
3. On first run, a browser window will open to complete the OAuth consent flow. A
   `token.json` file will then be created automatically to cache and refresh your session.

### 4. Never commit secrets

The following files contain secrets or local environment state and **must never be
committed to version control**:

- `.env`
- `credentials.json`
- `token.json`
- `.venv/`

These are already listed in `.gitignore`.

## How to run

```bash
python agent.py
```
