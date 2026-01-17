"""
ingest.py - Data Ingestion Pipeline for Repository Knowledge Base

This module handles the complete data pipeline for ingesting repository documentation:
1. Downloading repository source code from GitHub as a ZIP archive
2. Extracting and parsing markdown files with YAML frontmatter
3. Chunking documents using a sliding window approach for better retrieval
4. Building a searchable index using minsearch (BM25-style ranking)

Architecture:
    GitHub Repo --> ZIP Download --> Extract Markdown --> Parse Frontmatter
                                                              |
                                                              v
                                          Chunk Documents --> Build Index --> Ready for Search

Example Usage:
    >>> from ingest import index_data
    >>> index, branch = index_data("ethereum", "EIPs", chunk=True)
    >>> results = index.search("ERC-20 token standard", num_results=5)
"""

import io
import zipfile
import requests
import frontmatter
from minsearch import Index


def read_repo_data(
    repo_owner: str,
    repo_name: str,
    *,
    branches: tuple[str, ...] = ("main", "master"),
    include_exts: tuple[str, ...] = (".md", ".mdx"),
    include_prefixes: tuple[str, ...] = ("EIPS/",),
    timeout: int = 60,
) -> tuple[list[dict], str]:
    """
    Download and parse repository documentation from GitHub.

    This function downloads the repository as a ZIP archive, extracts markdown
    files matching the specified criteria, and parses YAML frontmatter metadata.

    Args:
        repo_owner: GitHub username or organization (e.g., "ethereum")
        repo_name: Repository name (e.g., "EIPs")
        branches: Tuple of branch names to try in order (falls back if first fails)
        include_exts: File extensions to include (default: markdown files)
        include_prefixes: Path prefixes to filter (e.g., only files in EIPS/ folder)
        timeout: HTTP request timeout in seconds

    Returns:
        Tuple of (documents_list, branch_used) where each document contains:
            - content: The markdown body text
            - filename: Original path in ZIP archive
            - path: Repository-relative path (without archive prefix)
            - branch: Git branch name
            - repo_owner, repo_name: Repository identifiers
            - Plus all YAML frontmatter fields (title, author, status, etc.)

    Raises:
        RuntimeError: If all branch download attempts fail

    Example:
        >>> docs, branch = read_repo_data("ethereum", "EIPs")
        >>> print(f"Found {len(docs)} documents from {branch} branch")
        >>> print(docs[0].keys())
        dict_keys(['content', 'filename', 'path', 'repo_owner', 'repo_name', 'branch', 'eip', 'title', ...])
    """
    last_err = None

    # Try each branch in order until one succeeds
    for branch in branches:
        # GitHub's codeload service provides direct ZIP downloads
        url = f"https://codeload.github.com/{repo_owner}/{repo_name}/zip/refs/heads/{branch}"

        try:
            # Download the repository as a ZIP archive
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            # Open ZIP directly from bytes in memory (no temp file needed)
            zf = zipfile.ZipFile(io.BytesIO(resp.content))

            docs = []
            for file_info in zf.infolist():
                name = file_info.filename
                name_lower = name.lower()

                # Filter by file extension (markdown files only)
                if not name_lower.endswith(include_exts):
                    continue

                # Strip the archive prefix "<repo>-<branch>/" to get clean repo path
                # Example: "EIPs-master/EIPS/eip-1.md" -> "EIPS/eip-1.md"
                parts = name.split("/", 1)
                if len(parts) != 2:
                    continue
                path = parts[1]  # Repository-relative path

                # Filter by path prefix (e.g., only files under EIPS/ directory)
                if include_prefixes and not path.startswith(include_prefixes):
                    continue

                # Parse the markdown file with frontmatter
                with zf.open(file_info) as f_in:
                    raw = f_in.read()
                    # python-frontmatter parses YAML header and markdown body
                    post = frontmatter.loads(raw)

                    # Convert to dict and add metadata
                    data = post.to_dict()  # Includes frontmatter fields
                    data["content"] = post.content  # Markdown body
                    data["filename"] = name  # Original archive path
                    data["path"] = path  # Clean repo path
                    data["repo_owner"] = repo_owner
                    data["repo_name"] = repo_name
                    data["branch"] = branch
                    docs.append(data)

            zf.close()
            return docs, branch

        except Exception as e:
            # Store error and try next branch
            last_err = e

    raise RuntimeError(f"Failed to download repo from branches {branches}. Last error: {last_err}")


def sliding_window(text: str, size: int, step: int) -> list[dict]:
    """
    Create overlapping text chunks using a sliding window approach.

    This technique ensures that information spanning chunk boundaries
    isn't lost, as adjacent chunks will have overlapping content.

    Args:
        text: The full text to chunk
        size: Maximum size of each chunk in characters
        step: Number of characters to advance for each chunk (overlap = size - step)

    Returns:
        List of dicts with 'start' position and 'content' for each chunk

    Example:
        >>> chunks = sliding_window("Hello World Example", size=10, step=5)
        >>> for c in chunks:
        ...     print(f"Position {c['start']}: '{c['content']}'")
        Position 0: 'Hello Worl'
        Position 5: 'World Exam'
        Position 10: 'Example'

    Visual representation:
        Text: |--------------------| (20 chars)

        Chunk 1: |==========|          (pos 0-10)
        Chunk 2:      |==========|     (pos 5-15, overlaps with chunk 1)
        Chunk 3:           |==========| (pos 10-20, overlaps with chunk 2)
    """
    if size <= 0 or step <= 0:
        raise ValueError("size and step must be positive")

    out = []
    n = len(text)

    for i in range(0, n, step):
        batch = text[i : i + size]
        out.append({"start": i, "content": batch})

        # Stop if we've captured everything to the end
        if i + size > n:
            break

    return out


def chunk_documents(docs: list[dict], size: int = 2000, step: int = 1000) -> list[dict]:
    """
    Apply sliding window chunking to a list of documents.

    Breaks each document into overlapping chunks while preserving
    all metadata from the original document.

    Args:
        docs: List of document dictionaries with 'content' field
        size: Chunk size in characters (default: 2000)
        step: Step size in characters (default: 1000, creating 50% overlap)

    Returns:
        List of chunk dictionaries, each containing:
            - content: The chunked text
            - start: Character position in original document
            - All other fields from the original document

    Example:
        >>> docs = [{"content": "Long document text...", "title": "Example"}]
        >>> chunks = chunk_documents(docs, size=500, step=250)
        >>> print(len(chunks))  # Multiple chunks from one document
        >>> print(chunks[0]["title"])  # Metadata preserved: "Example"
    """
    chunks = []

    for doc in docs:
        # Copy all metadata fields
        base = doc.copy()
        # Extract and remove full content
        full = base.pop("content", "")

        # Create chunks with sliding window
        for ch in sliding_window(full, size=size, step=step):
            # Merge chunk data with original metadata
            ch.update(base)
            chunks.append(ch)

    return chunks


def index_data(
    repo_owner: str,
    repo_name: str,
    *,
    branches: tuple[str, ...] = ("main", "master"),
    chunk: bool = True,
    chunking_params: dict | None = None,
) -> tuple[Index, str]:
    """
    Main pipeline: Download, parse, chunk, and index repository documentation.

    This is the primary entry point for building a searchable knowledge base
    from a GitHub repository's documentation.

    Args:
        repo_owner: GitHub username or organization
        repo_name: Repository name
        branches: Branch names to try in order
        chunk: Whether to split documents into overlapping chunks
        chunking_params: Dict with 'size' and 'step' for chunking
                        (default: {"size": 2000, "step": 1000})

    Returns:
        Tuple of (minsearch.Index, branch_used) ready for searching

    Example:
        >>> index, branch = index_data("ethereum", "EIPs", chunk=True)
        >>> print(f"Indexed from {branch} branch")

        >>> # Search the index
        >>> results = index.search("ERC-20 token", num_results=5)
        >>> for doc in results:
        ...     print(f"- {doc['path']}: {doc['content'][:100]}...")

    Pipeline Flow:
        1. read_repo_data() -> Download & parse markdown files
        2. chunk_documents() -> Split into overlapping chunks (if enabled)
        3. Index.fit() -> Build BM25 search index on content, path, filename
    """
    # Step 1: Download and parse repository
    docs, branch = read_repo_data(repo_owner, repo_name, branches=branches)

    # Step 2: Chunk documents for better retrieval (optional)
    if chunk:
        if chunking_params is None:
            chunking_params = {"size": 2000, "step": 1000}
        docs = chunk_documents(docs, **chunking_params)

    # Step 3: Build search index
    # minsearch uses BM25-style ranking on specified text fields
    index = Index(text_fields=["content", "path", "filename"])
    index.fit(docs)

    return index, branch
