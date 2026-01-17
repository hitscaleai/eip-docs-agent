"""
logs.py - Interaction Logging and Telemetry

This module provides logging functionality to persist agent interactions
for analysis, debugging, and improvement. Each conversation is saved as
a structured JSON file with full context.

Log Structure:
    ┌─────────────────────────────────────────────────────────────┐
    │  Log Entry (JSON File)                                       │
    ├─────────────────────────────────────────────────────────────┤
    │  {                                                           │
    │    "agent_name": "eip_agent_v1",                            │
    │    "system_prompt": "You are a helpful assistant...",       │
    │    "provider": "openai",                                     │
    │    "model": "gpt-4o-mini",                                  │
    │    "tools": ["search"],                                      │
    │    "messages": [                                             │
    │      { "kind": "request", "parts": [...], "timestamp": ...},│
    │      { "kind": "response", "parts": [...], ...}             │
    │    ],                                                        │
    │    "source": "user"                                          │
    │  }                                                           │
    └─────────────────────────────────────────────────────────────┘

File Naming:
    {agent_name}_{YYYYMMDD}_{HHMMSS}_{random_hex}.json
    Example: eip_agent_v1_20240115_143022_a1b2c3.json

Example Usage:
    >>> from logs import log_interaction_to_file
    >>> filepath = log_interaction_to_file(agent, result.new_messages())
    >>> print(f"Logged to: {filepath}")
"""

import os
import json
import secrets
from pathlib import Path
from datetime import datetime, date

from pydantic_ai.messages import ModelMessagesTypeAdapter


# Directory for storing interaction logs
# Configurable via LOGS_DIRECTORY environment variable
LOG_DIR = Path(os.getenv("LOGS_DIRECTORY", "logs"))
LOG_DIR.mkdir(exist_ok=True)  # Create if it doesn't exist


def log_entry(agent, messages, source: str = "user") -> dict:
    """
    Create a structured log entry from agent interaction.

    Extracts relevant information from the agent and messages to create
    a complete record of the interaction for later analysis.

    Args:
        agent: PydanticAI Agent instance
        messages: List of message objects from agent.run() result
        source: Origin of the interaction (default: "user")

    Returns:
        Dictionary containing:
            - agent_name: Identifier for the agent
            - system_prompt: The instructions given to the agent
            - provider: LLM provider (e.g., "openai")
            - model: Model name (e.g., "gpt-4o-mini")
            - tools: List of tool names available to agent
            - messages: Serialized message history
            - source: Origin of interaction

    Example:
        >>> entry = log_entry(agent, messages)
        >>> print(entry["agent_name"])  # "eip_agent_v1"
        >>> print(entry["tools"])  # ["search"]
    """
    # Extract tool names from agent's toolsets
    tools = []
    for ts in agent.toolsets:
        tools.extend(ts.tools.keys())

    # Serialize messages using PydanticAI's type adapter
    # This handles conversion of complex message objects to dicts
    dict_messages = ModelMessagesTypeAdapter.dump_python(messages)

    return {
        "agent_name": agent.name,
        "system_prompt": agent._instructions,
        "provider": agent.model.system,  # e.g., "openai"
        "model": agent.model.model_name,  # e.g., "gpt-4o-mini"
        "tools": tools,
        "messages": dict_messages,
        "source": source,
    }


def _ts_str(entry_messages: list[dict]) -> str:
    """
    Extract timestamp string from messages for filename generation.

    Handles multiple timestamp formats:
    - datetime objects (converted to string)
    - ISO format strings (parsed and reformatted)
    - Missing timestamps (falls back to current UTC time)

    Args:
        entry_messages: List of serialized message dictionaries

    Returns:
        Formatted timestamp string: "YYYYMMDD_HHMMSS"

    Example:
        >>> ts = _ts_str([{"timestamp": "2024-01-15T14:30:22Z"}])
        >>> print(ts)  # "20240115_143022"
    """
    # Get timestamp from the last message in the conversation
    ts = entry_messages[-1].get("timestamp")

    if isinstance(ts, datetime):
        # Already a datetime object
        dt = ts
    elif isinstance(ts, str):
        # Parse ISO format string (handle 'Z' suffix for UTC)
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    else:
        # Fallback to current UTC time
        dt = datetime.utcnow()

    return dt.strftime("%Y%m%d_%H%M%S")


def serializer(obj):
    """
    Custom JSON serializer for non-standard types.

    Handles datetime and date objects that appear in frontmatter
    metadata (e.g., document creation dates, last modified dates).

    Args:
        obj: Object that json.dump() couldn't serialize

    Returns:
        ISO format string representation

    Raises:
        TypeError: If object type is not handled

    Example:
        >>> import json
        >>> from datetime import date
        >>> json.dumps({"created": date(2024, 1, 15)}, default=serializer)
        '{"created": "2024-01-15"}'
    """
    # Handle both datetime and date objects
    # Frontmatter often contains date fields that need serialization
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def log_interaction_to_file(agent, messages, source: str = "user") -> Path:
    """
    Save agent interaction to a JSON log file.

    Creates a unique filename using timestamp and random hex suffix,
    then writes the complete interaction log to disk.

    Args:
        agent: PydanticAI Agent instance
        messages: List of message objects from agent run
        source: Origin of interaction (default: "user")

    Returns:
        Path to the created log file

    File Format:
        - Pretty-printed JSON (indent=2)
        - UTF-8 encoding
        - Custom serializer for datetime objects

    Example:
        >>> filepath = log_interaction_to_file(agent, result.new_messages())
        >>> print(filepath)
        # logs/eip_agent_v1_20240115_143022_a1b2c3.json

    Log File Location:
        Default: ./logs/
        Override: Set LOGS_DIRECTORY environment variable
    """
    # Create structured log entry
    entry = log_entry(agent, messages, source)

    # Generate unique filename components
    ts_str = _ts_str(entry["messages"])  # Timestamp from last message
    rand_hex = secrets.token_hex(3)  # Random suffix for uniqueness

    # Construct filename: {agent_name}_{timestamp}_{random}.json
    filename = f"{agent.name}_{ts_str}_{rand_hex}.json"
    filepath = LOG_DIR / filename

    # Write log entry to file
    with filepath.open("w", encoding="utf-8") as f_out:
        json.dump(entry, f_out, indent=2, default=serializer)

    return filepath
