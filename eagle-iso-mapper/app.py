import streamlit as st
import xml.etree.ElementTree as ET
import openpyxl
import io
import time

from src.config import settings
# Import the decoupled mapping logic
from src.mapping.eagle_to_iso import run_eagle_to_iso_mapping
from src.mapping.iso_to_eagle import run_iso_to_eagle_mapping

# set up web page
st.set_page_config(page_title="EAGLE / ISO Mapper", layout="wide")
st.title("🦅 EAGLE ↔️ ISO 19144-2 Mapper")

# --- INITIALISIERUNG SESSION STATE ---
if "log_text" not in st.session_state:
    st.session_state.log_text = ""
if "mapped_data" not in st.session_state:
    st.session_state.mapped_data = None
if "mapped_filename" not in st.session_state:
    st.session_state.mapped_filename = None

def log(msg: str):
    """Appends a message to the log and forces a UI update."""
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.log_text += f"[{timestamp}] {msg}\n"

def clear_logs_and_data():
    st.session_state.log_text = ""
    st.session_state.mapped_data = None
    st.session_state.mapped_filename = None

# --- validation ---
def is_valid_excel(uploaded_file) -> bool:
    try:
        wb = openpyxl.load_workbook(uploaded_file, read_only=True)
        return True
    except Exception as e:
        st.error(f"Excel Validierungsfehler: {e}")
        return False

def is_valid_xml(uploaded_file) -> bool:
    try:
        # Da uns XSDs fehlen, prüfen wir zumindest auf Wohlgeformtheit
        ET.parse(uploaded_file)
        uploaded_file.seek(0) # Pointer zurücksetzen für späteren Read
        return True
    except Exception as e:
        st.error(f"XML Validierungsfehler: {e}")
        return False

# --- UI TABS ---
tab1, tab2, tab3 = st.tabs(["📊 EAGLE ➔ ISO (Excel to XML)", "📄 ISO ➔ EAGLE (XML to Excel)", "⚙️ Admin (YAML)"])

# ==========================================
# TAB 1: EAGLE TO ISO
# ==========================================
with tab1:
    st.header("Upload EAGLE Matrix (Excel)")
    uploaded_excel = st.file_uploader("Wähle eine formatierte Excel-Datei", type=["xlsx"], key="up_excel", on_change=clear_logs_and_data)

    is_valid = False
    if uploaded_excel is not None:
        is_valid = is_valid_excel(uploaded_excel)
        if is_valid:
            st.success("Datei erfolgreich eingelesen und valide.")

    if st.button("Map to ISO", disabled=not is_valid, type="primary"):
        clear_logs_and_data()
        log(f"Loaded file: '{uploaded_excel.name}'")

        # Execute Mapping, passing the log function as a callback
        result_bytes = run_eagle_to_iso_mapping(uploaded_excel.getvalue(), log_callback=log)

        st.session_state.mapped_data = result_bytes
        st.session_state.mapped_filename = uploaded_excel.name.replace(".xlsx", "_mapped.xml")
        log("✅ Mapping successfully completed!")
        st.rerun()

# ==========================================
# TAB 2: ISO TO EAGLE
# ==========================================
with tab2:
    st.header("Upload LChS Export (XML)")

    # UI configuration
    col1, col2 = st.columns(2, gap="small")
    with col1:
        use_fuzzy = st.checkbox("Enable Fuzzy Mapping (Singular/Plural)", value=True, help="Automatically map LC_Tree to Trees")
    with col2:
        force_hierarchical = st.checkbox("Force Hierarchical Parser", value=False, help="Use if standard detection fails")

    uploaded_xml = st.file_uploader("Wähle eine LChS XML-Datei", type=["xml"], key="up_xml", on_change=clear_logs_and_data)

    is_valid = False
    if uploaded_xml is not None:
        is_valid = is_valid_xml(uploaded_xml)
        if is_valid:
            st.success("XML is well-formed and valid.")

    if st.button("Map to EAGLE", disabled=not is_valid, type="primary"):
        clear_logs_and_data()

        # Übergabe der Checkbox-Werte
        result_bytes = run_iso_to_eagle_mapping(
            uploaded_xml.getvalue(),
            log_callback=log,
            use_fuzzy=use_fuzzy,
            force_hierarchical=force_hierarchical
        )

        st.session_state.mapped_data = result_bytes
        st.session_state.mapped_filename = uploaded_xml.name.replace(".xml", "_mapped.xlsx")
        log("✅ Mapping successfully completed!")
        st.rerun()

# ==========================================
# TAB 3: ADMIN (YAML Viewer)
# ==========================================
with tab3:
    # 1. MAPPING YAML (Editable)
    st.subheader("Mapping Aliases (mappings.yaml)")
    with open(settings.MAPPING_CONFIG_PATH, "r") as f:
        current_yaml = f.read()

    new_yaml = st.code(current_yaml, language="yaml", height=380)

    if st.button("Save Mapping Aliases"):
        try:
            yaml.safe_load(new_yaml)
            with open(settings.MAPPING_CONFIG_PATH, "w") as f:
                f.write(new_yaml)
            st.success("Saved!")
        except Exception as e:
            st.error(f"Error: {e}")

    # 2. LinkML schema (read-only)
    st.subheader("LinkML Model (read-only)")
    if settings.LINKML_MODEL_PATH.exists():
        with open(settings.LINKML_MODEL_PATH, "r") as g:
            linkml_yaml = g.read()
    else:
        linkml_yaml ="LinkML model file not found."

    st.code(linkml_yaml, language="yaml", height=200)

# ==========================================
# GEMEINSAMER UNTERER BEREICH (Log & Download)
# ==========================================
st.divider()

col_log, col_download = st.columns([3, 1])

with col_log:
    st.subheader("Workflow Log")
    # Das Textfeld passt sich automatisch an (bei Streamlit durch st.container() / st.code())
    if st.session_state.log_text:
        st.code(st.session_state.log_text, language="text")
    else:
        st.caption("Noch keine Aktionen durchgeführt.")

with col_download:
    st.subheader("Export")
    if st.session_state.mapped_data is not None:
        mime_type = "application/xml" if st.session_state.mapped_filename.endswith(".xml") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        st.download_button(
            label="⬇️ Download Mapped File",
            data=st.session_state.mapped_data,
            file_name=st.session_state.mapped_filename,
            mime=mime_type,
            type="primary",
            use_container_width=True
        )
    else:
        st.info("Download steht nach erfolgreichem Mapping zur Verfügung.")