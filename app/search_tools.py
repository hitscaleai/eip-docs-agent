"""
search_tools.py - Search Tool for PydanticAI Agent

This module provides a search tool that the AI agent uses to retrieve
relevant documents from the indexed repository. The tool wraps the
minsearch index and is registered with the PydanticAI agent.

How it works:
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │   AI Agent      │────▶│   SearchTool    │────▶│  minsearch      │
    │   (LLM call)    │     │   .search()     │     │  Index          │
    └─────────────────┘     └─────────────────┘     └─────────────────┘
           │                        │                       │
           │  "Find ERC-20 docs"    │  query="ERC-20"      │  BM25 ranking
           └────────────────────────┴───────────────────────┘
                                    │
                                    ▼
                            Top 5 matching documents

Example Usage:
    >>> tool = SearchTool(index)
    >>> results = tool.search("ERC-20 token standard")
    >>> for doc in results:
    ...     print(doc["path"], doc["content"][:100])
"""

from typing import Any, List


class SearchTool:
    """
    Search tool wrapper for minsearch index.

    This class provides a search method that can be registered as a tool
    with PydanticAI agents. When the agent needs to find information,
    it calls this search method with a natural language query.

    Attributes:
        index: minsearch.Index object containing indexed documents

    Example:
        >>> from ingest import index_data
        >>> index, branch = index_data("ethereum", "EIPs")
        >>> tool = SearchTool(index)
        >>> results = tool.search("What is EIP-1559?")
        >>> print(f"Found {len(results)} relevant documents")
    """

    def __init__(self, index):
        """
        Initialize SearchTool with a minsearch index.

        Args:
            index: A fitted minsearch.Index object containing
                   documents with 'content', 'path', and 'filename' fields
        """
        self.index = index

    def search(self, query: str) -> List[Any]:
        """
        Search the index for documents matching the query.

        This method is called by the PydanticAI agent during inference.
        The agent will formulate a search query based on the user's
        question and use the results to generate an informed response.

        Args:
            query: Natural language search query
                   Example: "ERC-20 token interface"

        Returns:
            List of top 5 matching documents, each containing:
                - content: The document text (or chunk)
                - path: Repository-relative file path
                - filename: Original filename in archive
                - start: Chunk start position (if chunked)
                - Plus any frontmatter fields (title, author, etc.)

        Example:
            >>> results = tool.search("gas optimization")
            >>> for doc in results:
            ...     print(f"Found in: {doc['path']}")
            ...     print(f"Content: {doc['content'][:200]}...")
        """
        # Use minsearch's BM25-style ranking to find relevant documents
        # Returns top 5 results sorted by relevance score
        return self.index.search(query, num_results=5)
