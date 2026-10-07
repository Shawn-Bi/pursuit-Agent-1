"""Quick smoke test: call an OpenRouter model through strands-agents' LiteLLM provider."""

import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.litellm import LiteLLMModel

# Load OPENROUTER_API_KEY (and any other vars) from the .env file in the project root.
load_dotenv()

api_key = os.environ["OPENROUTER_API_KEY"]

# Fail fast with a clear local error instead of a confusing remote 401 if the
# .env value isn't a real OpenRouter key (OpenRouter keys start with "sk-or-").
if not api_key or not api_key.startswith("sk-or-"):
    raise RuntimeError(
        "OPENROUTER_API_KEY in .env does not look like a valid OpenRouter key "
        "(expected it to start with 'sk-or-'). Get a real key from "
        "https://openrouter.ai/keys and update .env."
    )

# LiteLLM talks to OpenRouter's OpenAI-compatible API. client_args are passed
# straight through to the underlying litellm.completion() call.
model = LiteLLMModel(
    client_args={
        "api_key": api_key,
        "base_url": "https://openrouter.ai/api/v1",
    },
    model_id="openrouter/openrouter/free",
    params={"max_tokens": 256},
)

# No tools: this is a plain conversational agent.
agent = Agent(model=model, tools=[])

result = agent("Say hello and tell me what model you are in one sentence.")

print(result)
