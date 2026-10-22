"""EAGLE Eye: spot EAGLE land cover, land use and land characteristics in a class description.

Run with:  uv run streamlit run app.py
"""

import streamlit as st

from eagle_eye.analysis import analyze
from eagle_eye import isoexport
from eagle_eye.overrides import Override, clear_bcv, put, reanchor, remove, reset
from eagle_eye.readers import SUPPORTED_TYPES, read_upload
from eagle_eye.resolver import Resolver
from eagle_eye.samples import SAMPLES
from eagle_eye.ui import annotator
from eagle_eye.vocabulary import load_vocabulary

st.set_page_config(page_title="EAGLE Eye", page_icon="🦅", layout="wide", initial_sidebar_state="collapsed")

ANNOTATED, EDIT = "🖍️ Annotated", "✏️ Edit"
FIRST_SAMPLE = next(iter(SAMPLES))

state = st.session_state
state.setdefault("doc", SAMPLES[FIRST_SAMPLE])
state.setdefault("doc_name", "natural-grassland")
state.setdefault("mode", ANNOTATED)
state.setdefault("selection", None)  # {entries: [keys], mention: id | None}
state.setdefault("pending", None)  # {start, end}: text marked by the user, waiting for a class
state.setdefault("overrides", [])
state.setdefault("pick_round", 0)  # new key for the class picker after each use, which clears it
state.setdefault("reselect", None)  # (start, end) of the highlight to select after the next analysis
state.setdefault("notice", None)


@st.cache_resource
def warm_up_export() -> bool:
    isoexport.warm_up()  # the mapper takes many seconds to import: start now, not at the first export
    return True


warm_up_export()

BCV_OPTIONS = ["automatic", "X", "1", "2", "3", "4", "5"]
BCV_NAMES = {
    "automatic": "automatic (suggested from the text)",
    "X": "X · excluded by definition",
    "1": "1 · optional, typical",
    "2": "2 · selective mandatory (either-or)",
    "3": "3 · cumulative mandatory (and)",
    "4": "4 · paired mandatory (at least two)",
    "5": "5 · exclusive (only this one)",
}


@st.cache_resource
def picker_options() -> tuple[list[str], dict[str, str]]:
    """All selectable EAGLE elements (headings are modules, not classes) and their picker labels."""
    vocab = load_vocabulary()
    concepts = [c for c in vocab.concepts if c.level > 0 and not c.is_heading]
    return [c.code for c in concepts], {c.code: f"{c.code} · {c.label}" for c in concepts}


# ---------------------------------------------------------------- callbacks


def set_document(text: str, name: str, keep_overrides: bool):
    if keep_overrides:
        state.overrides, dropped = reanchor(state.overrides, text)
        state.notice = f"{dropped} manual change(s) no longer apply to the edited text." if dropped else None
    else:
        state.overrides, state.notice = [], None
    state.doc, state.doc_name = text, name
    state.selection = state.pending = None


def commit_editor():
    set_document(state.editor, state.doc_name, keep_overrides=True)


def load_sample():
    if state.sample is None:
        return
    set_document(SAMPLES[state.sample], state.sample.lower().replace(" ", "-"), keep_overrides=False)
    state.mode = ANNOTATED


def load_upload():
    file = state.upload
    if file is None:
        return
    try:
        text = read_upload(file.name, file.getvalue())
    except ValueError as err:
        state.upload_error = str(err)
        return
    state.upload_error = None
    set_document(text, file.name.rsplit(".", 1)[0], keep_overrides=False)
    state.mode = ANNOTATED


def apply_pick():
    code = state.get(f"pick_{state.pick_round}")
    if not code:
        return
    if state.pending:
        p = state.pending
        new = Override(p["start"], p["end"], state.doc[p["start"] : p["end"]], "add", code)
    else:
        cur = state.current
        new = Override(cur["start"], cur["end"], cur["text"], "replace", code, state.get("item_index", 0))
    state.overrides = put(state.overrides, new)
    state.pending, state.reselect = None, (new.start, new.end)
    state.pick_round += 1


def apply_bcv():
    cur, index = state.current, state.get("item_index", 0)
    value = state[f"bcv_{state.pick_round}_{cur['start']}_{cur['end']}_{index}"]
    if value == "automatic":
        state.overrides = clear_bcv(state.overrides, cur["start"], cur["end"], index)
    else:
        state.overrides = put(state.overrides, Override(cur["start"], cur["end"], cur["text"], "bcv", value, index))
    state.reselect = (cur["start"], cur["end"])
    state.pick_round += 1


def cancel_pending():
    state.pending = None


def remove_current():
    cur = state.current
    state.overrides = remove(state.overrides, cur["start"], cur["end"], cur["text"])
    state.selection = None


def reset_current():
    cur = state.current
    state.overrides = reset(state.overrides, cur["start"], cur["end"])
    state.reselect = (cur["start"], cur["end"])


# ---------------------------------------------------------------- analysis

vocab = load_vocabulary()
analysis = analyze(state.doc, vocab, state.overrides)
payload = analysis.to_payload()

if state.pending and state.pending["end"] > len(state.doc):
    state.pending = None

if state.reselect:  # follow the highlight the user just changed or added
    span, state.reselect = state.reselect, None
    hit = next((m for m in payload["mentions"] if (m["start"], m["end"]) == span), None)
    state.selection = {"entries": hit["entries"], "mention": hit["id"]} if hit else None

selected = state.selection
if selected and not set(selected["entries"]) <= {e["key"] for e in payload["entries"]}:
    state.selection = selected = None  # the text changed under the selection

mention = None
if selected and selected.get("mention") is not None and not state.pending:
    mention = analysis.mentions[selected["mention"]] if selected["mention"] < len(analysis.mentions) else None
    state.current = {"start": mention.start, "end": mention.end, "text": mention.text} if mention else None


def assign_panel():
    """Pick an EAGLE class for the marked text, or a different class for the active highlight."""
    resolver = Resolver(vocab)
    codes, labels = picker_options()
    if state.pending:
        p = state.pending
        wording = state.doc[p["start"] : p["end"]]
        title, suggested = f"Add a highlight for “{wording}”", resolver.suggest(wording, 8)
    elif mention:
        current = [i.code for i in mention.items if i.code]
        # nearest first: the neighbours in the EAGLE hierarchy, then what the resolver considered, then text matches
        near = []
        for code in current:
            concept = vocab.get(code)
            near += [c.code for c in vocab.path(code)[1:-1]]
            near += [c.code for c in vocab.children(concept.parent or "") if c.code != code]
            near += [c.code for c in vocab.children(code)]
        suggested = list(dict.fromkeys(near + [a.code for a in mention.alternatives] + resolver.suggest(mention.text, 6)))
        suggested = [c for c in suggested if c in labels and c not in current][:10]
        title = f"Change the class of “{mention.text}”"
    else:
        return
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if mention and len(mention.items) > 1:
            if state.get("item_for") != (mention.start, mention.end):
                state.item_index, state.item_for = 0, (mention.start, mention.end)
            st.radio(
                "Which of its classes?",
                list(range(len(mention.items))),
                format_func=lambda i: labels.get(mention.items[i].code, "no class"),
                key="item_index",
                horizontal=True,
            )
        else:
            state.item_index = 0
        ordered = suggested + [c for c in codes if c not in suggested]
        st.selectbox(
            "EAGLE class",
            ordered,
            index=None,
            format_func=lambda c: ("★ " if c in suggested else "") + labels[c],
            placeholder="Search the EAGLE classes… (★ = suggested)",
            key=f"pick_{state.pick_round}",
            on_change=apply_pick,
            label_visibility="collapsed",
        )
        if mention and not state.pending:
            item = mention.items[min(state.get("item_index", 0), len(mention.items) - 1)]
            if item.code and not vocab.get(item.code).is_parameter:
                value = item.bcv if item.bcv_basis == "manual" else "automatic"
                suggestion = f"suggested {item.bcv}" + (f": {item.bcv_reasons[0]}" if item.bcv_reasons else "") if item.bcv else "no bar code value"
                st.selectbox(
                    f"Bar code value ({suggestion})" if value == "automatic" else "Bar code value (set manually)",
                    BCV_OPTIONS,
                    index=BCV_OPTIONS.index(value),
                    format_func=BCV_NAMES.get,
                    key=f"bcv_{state.pick_round}_{mention.start}_{mention.end}_{state.get('item_index', 0)}",
                    on_change=apply_bcv,
                )
        if state.pending:
            st.button("Cancel", on_click=cancel_pending)
        else:
            changed = any(o.action == "replace" and (o.start, o.end) == (mention.start, mention.end) for o in state.overrides)
            manual = any(i.origin == "added" for i in mention.items)
            cols = st.columns(2)
            cols[0].button("Remove highlight", on_click=remove_current, width="stretch")
            if changed:
                cols[1].button("Reset to automatic", on_click=reset_current, width="stretch")
            elif manual:
                cols[1].caption("Manual highlight")


def export_panel(analysis):
    """ISO 19144-2 LChS XML, converted by the eagle-iso-mapper from the bar coded class."""
    if not isoexport.available():
        st.error(f"The eagle-iso-mapper was not found at {isoexport.ISO_MAPPER_DIR}. Keep it next to eagle-eye or set EAGLE_ISO_MAPPER_DIR.")
        return
    plan = isoexport.plan_export(analysis, vocab)
    name = st.text_input("Class name", state.doc_name, key=f"export_name_{state.doc_name}")
    code = st.text_input("Class code", "", placeholder="e.g. CLC321 (default: derived from the name)", key=f"export_code_{state.doc_name}")
    st.caption(f"{len(plan.written)} of {len(plan.written) + len(plan.not_written)} bar coded elements go into the XML.")
    for note in plan.notes:
        st.caption(f"⚠️ {note}")
    if plan.not_written:
        with st.expander(f"Not in the XML ({len(plan.not_written)})"):
            st.caption("The eagle-iso-mapper writes land cover components and irrigation / rice / hops characteristics.")
            for line in plan.not_written:
                st.caption(f"· {line}")
    st.download_button(
        "⬇ Download LChS XML",
        data=lambda: isoexport.to_lchs_xml(analysis, vocab, code, name).xml,
        file_name=f"{state.doc_name}.lchs.xml",
        mime="application/xml",
        width="stretch",
        help="ISO 19144-2 LChS XML for the FAO LChS tool. The first export after starting the app can take a while.",
    )


# ---------------------------------------------------------------- page

st.title("🦅 EAGLE Eye")
st.caption(
    "Find the three EAGLE building blocks in a land cover / land use description: "
    "**Land Cover** (LCC), **Land Use** (LUA) and **Land Characteristics** (LCH). "
    "Click a highlight to change its class, or select some text to add a highlight."
)

left, right = st.columns([1.15, 1], gap="large")

with left:
    st.segmented_control("View", [ANNOTATED, EDIT], key="mode", label_visibility="collapsed")

    if state.mode == EDIT:
        st.text_area(
            "Text",
            value=state.doc,
            key="editor",
            height=420,
            label_visibility="collapsed",
            placeholder="Paste a class definition here, then press Ctrl+Enter…",
            on_change=commit_editor,
        )
        text_event = None
    else:
        text_event = annotator(payload, "text", selected, key="text-pane", pending=state.pending)

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
    if state.get("upload_error"):
        st.error(state.upload_error)
    if state.notice:
        st.warning(state.notice)
    words = len(state.doc.split())
    manual_count = sum(1 for m in analysis.mentions for i in m.items if i.origin != "automatic")
    st.caption(f"{words} words · {len(analysis.mentions)} highlights" + (f" · {manual_count} changed by hand" if manual_count else ""))

with right:
    title_col, export_col = st.columns([3, 2], vertical_alignment="center")
    title_col.subheader("EAGLE classes", anchor=False)
    with export_col.popover("⬇ Export XML", width="stretch"):
        export_panel(analysis)
    assign_panel()
    class_event = annotator(payload, "classes", selected, key="class-pane")

    with st.expander("Highlight details"):
        st.dataframe(
            [
                {
                    "text": m.text,
                    "type": m.block,
                    "EAGLE class": f"{item.code} {vocab.get(item.code).label}" if item.code else "–",
                    "excluded": item.negated,
                    "confidence": item.confidence,
                    "BCV": item.bcv or "–",
                    "BCV why": "; ".join(item.bcv_reasons),
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
    if event and event["nonce"] != state.get(f"nonce_{name}"):
        state[f"nonce_{name}"] = event["nonce"]
        if event.get("range"):
            state.pending, state.selection = event["range"], None
        else:
            state.selection, state.pending = event["selection"], None
        st.rerun()
