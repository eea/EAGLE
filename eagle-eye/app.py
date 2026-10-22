"""EAGLE Eye: spot EAGLE land cover, land use and land characteristics in a class description.

Run with:  uv run streamlit run app.py
"""

import streamlit as st

from eagle_eye.analysis import analyze
from eagle_eye.readers import SUPPORTED_TYPES, read_upload
from eagle_eye.samples import SAMPLES
from eagle_eye.ui import annotator
from eagle_eye.vocabulary import load_vocabulary

st.set_page_config(page_title="EAGLE Eye", page_icon="🦅", layout="wide", initial_sidebar_state="collapsed")

ANNOTATED, EDIT = "🖍️ Annotated", "✏️ Edit"
FIRST_SAMPLE = next(iter(SAMPLES))

st.session_state.setdefault("doc", SAMPLES[FIRST_SAMPLE])
st.session_state.setdefault("mode", ANNOTATED)
st.session_state.setdefault("selection", None)


def commit_editor():
    st.session_state.doc = st.session_state.editor
    st.session_state.selection = None


def load_sample():
    if st.session_state.sample is None:
        return
    st.session_state.doc = SAMPLES[st.session_state.sample]
    st.session_state.mode = ANNOTATED
    st.session_state.selection = None


def load_upload():
    file = st.session_state.upload
    if file is None:
        return
    try:
        st.session_state.doc = read_upload(file.name, file.getvalue())
    except ValueError as err:
        st.session_state.upload_error = str(err)
        return
    st.session_state.upload_error = None
    st.session_state.mode = ANNOTATED
    st.session_state.selection = None


st.title("🦅 EAGLE Eye")
st.caption(
    "Find the three EAGLE building blocks in a land cover / land use description: "
    "**Land Cover** (LCC), **Land Use** (LUA) and **Land Characteristics** (LCH)."
)

analysis = analyze(st.session_state.doc)
payload = analysis.to_payload()

# Drop a selection that no longer exists after the text changed.
selected = st.session_state.selection
if selected and not set(selected["entries"]) <= {e["key"] for e in payload["entries"]}:
    st.session_state.selection = selected = None

left, right = st.columns([1.15, 1], gap="large")

with left:
    st.segmented_control("View", [ANNOTATED, EDIT], key="mode", label_visibility="collapsed")

    if st.session_state.mode == EDIT:
        st.text_area(
            "Text",
            value=st.session_state.doc,
            key="editor",
            height=420,
            label_visibility="collapsed",
            placeholder="Paste a class definition here, then press Ctrl+Enter…",
            on_change=commit_editor,
        )
        text_event = None
    else:
        text_event = annotator(payload, "text", selected, key="text-pane")

    upload_col, sample_col = st.columns([3, 2], vertical_alignment="bottom")
    upload_col.file_uploader(
        f"Upload a text file ({', '.join('.' + t for t in SUPPORTED_TYPES)})",
        type=SUPPORTED_TYPES,
        key="upload",
        on_change=load_upload,
    )
    sample_col.selectbox(
        "Example",
        list(SAMPLES),
        index=None,
        placeholder="Load an example…",
        key="sample",
        on_change=load_sample,
    )
    if st.session_state.get("upload_error"):
        st.error(st.session_state.upload_error)
    words = len(st.session_state.doc.split())
    st.caption(f"{words} words · {len(analysis.mentions)} highlights")

with right:
    st.subheader("EAGLE classes", anchor=False)
    class_event = annotator(payload, "classes", selected, key="class-pane")

    with st.expander("Highlight details"):
        vocab = load_vocabulary()
        st.dataframe(
            [
                {
                    "text": m.text,
                    "type": m.block,
                    "EAGLE class": f"{item.code} {vocab.get(item.code).label}" if item.code else "–",
                    "excluded": item.negated,
                    "confidence": item.confidence,
                    "alternatives": ", ".join(f"{a.code} ({a.score:.2f})" for a in m.alternatives),
                    "why": "; ".join(item.reasons),
                }
                for m in analysis.mentions
                for item in m.items
            ],
            hide_index=True,
            width="stretch",
        )

for name, event in (("text", text_event), ("classes", class_event)):
    if event and event["nonce"] != st.session_state.get(f"nonce_{name}"):
        st.session_state[f"nonce_{name}"] = event["nonce"]
        st.session_state.selection = event["selection"]
        st.rerun()
