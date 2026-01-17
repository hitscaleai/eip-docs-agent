"""
search_agent.py - AI Agent Configuration and Initialization

This module configures and instantiates the PydanticAI agent that powers
the repository Q&A system. The agent is equipped with a search tool to
retrieve relevant documentation before answering questions.

Key Components:
    - System prompt template with repository context
    - Agent initialization with configurable LLM model
    - Search tool integration for RAG (Retrieval-Augmented Generation)

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    PydanticAI Agent                          │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │  System Prompt (repo context + instructions)          │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                           │                                  │
    │                           ▼                                  │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │  LLM (gpt-4o-mini or configured model)               │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                           │                                  │
    │                           ▼                                  │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │  Tools: [search] → Retrieves relevant documents       │   │
    │  └──────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘

Example Usage:
    >>> from search_agent import init_agent
    >>> agent = init_agent(index, "ethereum", "EIPs", "master")
    >>> result = await agent.run("What is ERC-20?")
"""

import os
from pydantic_ai import Agent
import search_tools


# System prompt template with placeholders for repository context
# This prompt instructs the agent how to behave and use the search tool
SYSTEM_PROMPT_TEMPLATE = """
You are a helpful assistant that answers questions about the repository documentation.

Use the search tool to find relevant information before answering.
If you find specific information through search, use it to provide accurate answers.

Always include references by citing the file(s) you used as GitHub links.
Base URL:
"https://github.com/{repo_owner}/{repo_name}/blob/{branch}/"
Format: [FILE PATH](FULL_GITHUB_LINK)

If the search doesn't return relevant results, say so and provide general guidance.
""".strip()


def init_agent(index, repo_owner: str, repo_name: str, branch: str) -> Agent:
    """
    Initialize and configure the PydanticAI agent with search capabilities.

    Creates an agent with:
    - A system prompt containing repository context and usage instructions
    - A search tool connected to the minsearch index
    - Configurable LLM model (via environment variable)

    Args:
        index: minsearch.Index object for document retrieval
        repo_owner: GitHub username or organization (e.g., "ethereum")
        repo_name: Repository name (e.g., "EIPs")
        branch: Git branch name (e.g., "master" or "main")

    Returns:
        Configured PydanticAI Agent ready for queries

    Environment Variables:
        MODEL_NAME: LLM model to use (default: "gpt-4o-mini")
                   Examples: "gpt-4", "gpt-4-turbo", "claude-3-sonnet"
        AGENT_NAME: Identifier for logging (default: "eip_agent_v1")

    Example:
        >>> import os
        >>> os.environ["MODEL_NAME"] = "gpt-4"  # Use GPT-4
        >>> agent = init_agent(index, "ethereum", "EIPs", "master")
        >>> print(agent.name)  # "eip_agent_v1"

    Agent Flow:
        1. User asks question
        2. Agent calls search tool to find relevant docs
        3. Agent synthesizes answer from search results
        4. Agent includes GitHub links to source files
    """
    # Format the system prompt with repository-specific context
    # This gives the agent knowledge about which repo it's helping with
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        repo_owner=repo_owner, repo_name=repo_name, branch=branch
    )

    # Initialize the search tool with the document index
    # The agent will call tool.search(query) to retrieve documents
    tool = search_tools.SearchTool(index=index)

    # Get model name from environment or use default
    # Supports OpenAI models (gpt-4o-mini, gpt-4, etc.)
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    # Create the PydanticAI agent
    # - name: Used for logging and identification
    # - instructions: System prompt that guides agent behavior
    # - tools: List of callable tools the agent can use
    # - model: LLM model identifier
    agent = Agent(
        name=os.getenv("AGENT_NAME", "eip_agent_v1"),
        instructions=system_prompt,
        tools=[tool.search],  # Agent can call the search function
        model=model_name,
    )

    return agent
