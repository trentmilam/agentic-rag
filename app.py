"""agentic-rag -- real IETF RFC/errata/IANA corpus, interactive chat UI.

    projects/agentic-rag/.venv/Scripts/python.exe app.py

Ask real questions about IETF protocol specifications, RFC authorship/status,
RFC errata, IANA registries, or which RFC obsoleted another one. Retrieval
answers are extractive and citation-gated: the retrieved source chunks ARE the
answer, or the system abstains rather than guess. The one exception is
obsoletion questions ("what replaced RFC 2616?"), answered by a deterministic
graph lookup over the real IETF Obsoletes/Obsoleted-by graph, not retrieval.
No LLM anywhere in the answer path.

Standalone: no network calls at query time, no dependency on anything outside
this repo + its sibling capability repo (consilium).
"""
from __future__ import annotations

import html
import json
import os
import sys

AGENTIC_RAG_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AGENTIC_RAG_ROOT)

from agenticrag._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

import gradio as gr  # noqa: E402

from consilium.compute import answer_v3  # noqa: E402

from agenticrag.bootstrap import build_registry, build_router  # noqa: E402
from agenticrag.embed_config import get_embedder               # noqa: E402

print("Building the agentic-rag registry (Qdrant-backed; a one-time ~60s scan for the\n"
      "poison-quarantine corpus, then queries hit Qdrant live -- progress below)...",
      flush=True)
EMBEDDER = get_embedder()
REGISTRY = build_registry(EMBEDDER)
ROUTER = build_router(REGISTRY, EMBEDDER)

EXAMPLES = [
    "What obsoleted RFC 2616, the HTTP/1.1 specification?",
    "How does IP fragmentation and reassembly work in the Internet Protocol?",
    "Who authored RFC 2119 and when was it published?",
    "What errata have been reported against RFC 5322?",
    "What port is registered for HTTPS in the IANA service names registry?",
    "Is RFC 791 still current?",
    "What's the best way to season a cast iron skillet before first use?",
]

# ---------------------------------------------------------------------------
# Theme -- a quiet, neutral SaaS chrome (one surface, one accent, plain status
# pills), with a distinct teal accent for this tool's identity.
# ---------------------------------------------------------------------------
_BG = "#F7F8FA"
_SURFACE = "#FFFFFF"
_BORDER = "#E2E5EA"
_INK = "#14181F"
_INK_MUTED = "#5B6472"
_ACCENT = "#0F5C55"
_ACCENT_HOVER = "#137068"
_BLUE_TEXT, _BLUE_BG = "#1E40AF", "#DBEAFE"
_GREEN_TEXT, _GREEN_BG = "#166534", "#DCFCE7"
_GRAY_TEXT, _GRAY_BG = "#475569", "#F1F5F9"
_SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_MONO = "'SFMono-Regular', Consolas, 'Liberation Mono', ui-monospace, monospace"

THEME = gr.themes.Base(spacing_size="md", radius_size="md", font=[_SANS], font_mono=[_MONO]).set(
    body_background_fill=_BG,
    body_background_fill_dark=_BG,
    body_text_color=_INK,
    body_text_color_dark=_INK,
    body_text_color_subdued=_INK_MUTED,
    background_fill_primary=_SURFACE,
    background_fill_primary_dark=_SURFACE,
    block_background_fill=_SURFACE,
    block_background_fill_dark=_SURFACE,
    block_border_color=_BORDER,
    block_border_color_dark=_BORDER,
    block_label_text_color=_INK_MUTED,
    block_label_text_color_dark=_INK_MUTED,
    block_title_text_color=_INK,
    block_title_text_color_dark=_INK,
    input_background_fill=_SURFACE,
    input_background_fill_dark=_SURFACE,
    border_color_primary=_BORDER,
    border_color_primary_dark=_BORDER,
    button_primary_background_fill=_ACCENT,
    button_primary_background_fill_dark=_ACCENT,
    button_primary_background_fill_hover=_ACCENT_HOVER,
    button_primary_text_color="#FFFFFF",
    button_primary_text_color_dark="#FFFFFF",
)

CUSTOM_CSS = f"""
.gradio-container {{ font-family: {_SANS} !important; max-width: 900px !important; margin: 0 auto !important; }}
#hero h1 {{ font-size: 1.6rem; font-weight: 700; color: {_INK}; margin-bottom: 0.2rem; }}
#hero p {{ color: {_INK_MUTED}; font-size: 0.95rem; max-width: 68ch; }}
.pill {{
    display: inline-flex; align-items: center; gap: 0.35em; font-size: 0.76rem; font-weight: 600;
    padding: 0.18rem 0.6rem; border-radius: 999px; margin: 0 0.3rem 0.4rem 0;
}}
.pill-source {{ color: {_BLUE_TEXT}; background: {_BLUE_BG}; font-family: {_MONO}; }}
.pill-compute {{ color: {_GREEN_TEXT}; background: {_GREEN_BG}; }}
.pill-abstain {{ color: {_GRAY_TEXT}; background: {_GRAY_BG}; }}
.ans-headline {{ font-size: 0.9rem; color: {_INK_MUTED}; margin: 0 0 0.5rem; }}
.citation {{ padding: 0.5rem 0; border-top: 1px solid {_BORDER}; font-size: 0.92rem; line-height: 1.5; color: {_INK}; }}
.citation:first-of-type {{ border-top: none; }}
.citation-src {{
    display: block; font-family: {_MONO}; font-size: 0.76rem; color: {_INK_MUTED}; margin-top: 0.25rem;
}}
.ans-body pre {{
    font-family: {_MONO}; background: {_BG}; border: 1px solid {_BORDER}; border-radius: 8px;
    padding: 0.7rem 0.9rem; overflow-x: auto; font-size: 0.85rem;
}}
button:focus-visible, textarea:focus-visible, input:focus-visible {{ outline: 2px solid {_ACCENT} !important; outline-offset: 2px; }}
"""


def _render_compute(module: str, audited: dict) -> str:
    parts = [f'<span class="pill pill-compute">audited: {html.escape(module)}</span>']
    parts.append(
        f'<div class="ans-headline">deterministic: {audited.get("deterministic")} &middot; '
        f'{html.escape(str(audited.get("method", "n/a")))}</div>'
    )
    if not audited.get("ok"):
        parts.append(f'<div class="citation">{html.escape(str(audited.get("error", "unknown error")))}</div>')
        return "".join(parts)
    result = audited.get("result", {})
    if module == "supersession":
        status = result.get("status")
        successors = result.get("successors", [])
        if status == "obsoleted":
            body = f"Obsoleted by: {', '.join(successors)}"
        elif status == "current":
            body = "Still current -- nothing in the real index obsoletes it."
        else:
            body = "Not found in the live RFC index."
        parts.append(f'<div class="citation">{html.escape(body)}</div>')
    else:
        parts.append(f'<div class="ans-body"><pre>{html.escape(json.dumps(result, indent=2, default=str))}</pre></div>')
    return "".join(parts)


def _render_retrieval(a: dict) -> str:
    """``answer_v3``'s ``answer`` field is already ``compose()``'s fully-formatted,
    per-citation text (one "- claim [module/doc chunk_id, support=score]" line
    per kept citation) -- rendered here as one block, one line per kept
    citation."""
    modules = a.get("module") or []
    if isinstance(modules, str):
        modules = [modules]
    pills = "".join(f'<span class="pill pill-source">{html.escape(m)}</span>' for m in modules)
    body = "".join(f"<div class=\"citation\">{html.escape(line)}</div>"
                    for line in (a.get("answer") or "").splitlines() if line.strip())
    return pills + body


def _render_answer(a: dict) -> str:
    kind = a.get("kind")
    if kind == "abstain":
        return ('<span class="pill pill-abstain">no answer</span>'
                '<div class="ans-headline">Nothing in this corpus supported an answer -- '
                'honest abstain, not a guess.</div>')
    if kind == "compute":
        return _render_compute(a["module"], a["audited"])
    if kind == "mixed":
        parts = [_render_compute(c["module"], c["audited"]) for c in a.get("computed", [])]
        if a.get("answer"):
            parts.append(_render_retrieval(a))
        return "<hr>".join(parts)
    return _render_retrieval(a)  # retrieval


def respond(message: str, history: list):
    # Query-time routing + retrieval run as native Qdrant vector searches (~12s on
    # CPU at the full 321k-chunk scale, since Qdrant local mode is exact brute-force).
    # Yield an immediate status first -- Gradio streams it before the blocking
    # answer_v3 call returns -- so the UI shows real progress instead of a blank
    # indistinguishable from a hang.
    yield ("_Searching the corpus with Qdrant vector search + citation-gated compose "
           "(~12 seconds on CPU; no GPU is used at query time)..._")
    a = answer_v3(message, REGISTRY, EMBEDDER, ROUTER)
    yield _render_answer(a)


demo = gr.ChatInterface(
    fn=respond,
    title="agentic-rag",
    description=(
        "A cited, extractive RAG over the real IETF RFC/errata/IANA corpus, plus a "
        "deterministic real Obsoletes/Obsoleted-by graph lookup. Every claim traces "
        "to a real source chunk or a real graph fact, or the system says it doesn't know. "
        "Note: each query runs a live Qdrant vector search on CPU, so a reply takes ~12 seconds."
    ),
    examples=EXAMPLES,
    run_examples_on_click=True,
)

if __name__ == "__main__":
    demo.launch(share=False, inbrowser=False, theme=THEME, css=CUSTOM_CSS)
