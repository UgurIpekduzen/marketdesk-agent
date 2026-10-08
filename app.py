"""Deploy trial page.

A temporary page that answers one question before the real interface is
built: does the deploy platform have room for the embedding model and for
the MCP server as a child process? It holds no business logic; everything
it shows comes from src/.
"""

import platform
import time
from pathlib import Path

import streamlit as st

from src.knowledge.embedding import load_embedder
from src.mcp_server.client import call_tool

CGROUP = Path("/sys/fs/cgroup")
MB = 1024 * 1024


def read_number(path: Path) -> int | None:
    """A number from a system file, or None when it is missing or 'max'."""
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def process_memory_mb() -> int | None:
    """Memory this process holds right now."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def show_memory(label: str) -> None:
    """Show the process memory and what the platform counts and allows."""
    in_use = read_number(CGROUP / "memory.current")
    limit = read_number(CGROUP / "memory.max")
    columns = st.columns(3)
    columns[0].metric(f"{label}: this process", f"{process_memory_mb()} MB")
    columns[1].metric(
        "Container, all processes", f"{in_use // MB} MB" if in_use else "unknown"
    )
    columns[2].metric("Container limit", f"{limit // MB} MB" if limit else "none set")


@st.cache_resource
def embedder():
    """Load the model once per server process, not once per page view."""
    return load_embedder()


st.title("MarketDesk: deploy trial")
st.caption(f"Python {platform.python_version()} on {platform.machine()}")
show_memory("At start")

st.header("1. Embedding model")
question = st.text_input("Question", "Hasarlı ürünü kaç gün içinde iade edebilirim?")
if st.button("Embed the question"):
    started = time.perf_counter()
    model = embedder()
    loaded = time.perf_counter()
    vector = model.embed_queries([question])[0]
    done = time.perf_counter()
    st.write(
        f"{len(vector)} dimensions. Model ready in {loaded - started:.1f} s, "
        f"question embedded in {(done - loaded) * 1000:.0f} ms."
    )
    st.write("First values:", [round(float(value), 4) for value in vector[:5]])
    show_memory("After embedding")

st.header("2. MCP server as a child process")
if st.button("Start the server and call its status tool"):
    started = time.perf_counter()
    answer = call_tool("status")
    st.write(f"Answer in {time.perf_counter() - started:.1f} s:")
    st.json(answer)
    show_memory("After the call")
