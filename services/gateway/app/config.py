"""Gateway settings, all read from environment variables."""
import os

# Where the agent service lives. Inside the cluster this is the Kubernetes Service name.
AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8001")

# The agent calls an LLM, so give it room before the gateway gives up.
AGENT_TIMEOUT_SECONDS = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "60"))
