import streamlit as st
import xml.etree.ElementTree as ET
import openpyxl
import io
import time

from src.config import settings
# Import the decoupled mapping logic
from src.mapping.eagle_to_iso import run_eagle_to_iso_mapping
from src.mapping.iso_to_eagle import run_iso_to_eagle_mapping
from typing import Tuple, List

import streamlit as st
import time

# Session State initialisieren
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
if "mapped_data" not in st.session_state:
    st.session_state.mapped_data = None
if "mapped_filename" not in st.session_state:
    st.session_state.mapped_filename = None
if "selected_sheet" not in st.session_state:
    st.session_state.selected_sheet = None

class LiveLogger:
    def __init__(self):
        # Am Anfang gibt es noch kein UI-Element, an das wir senden können
        self.ui_container = None

    def set_container(self, container):
        """Biegt den Logger zur Laufzeit auf einen bestimmten Streamlit-Container um."""
        self.ui_container = container
        # Falls schon Logs im Session State sind, sofort einmal rendern
        self._render()

    def log(self, msg: str):
        """Fügt eine Nachricht hinzu und aktualisiert das UI (falls vorhanden)."""
        timestamp = time.strftime("%H:%M:%S")
        st.session_state.log_messages.append(f"[{timestamp}] {msg}")

        # Limit auf 15 Zeilen für den Live-Effekt
        if len(st.session_state.log_messages) > 15:
            st.session_state.log_messages.pop(0)

        # UI Update aufrufen
        self._render()

        # Der Amiga-Hack für den WebSocket ;-)
        time.sleep(0.01)

    def _render(self):
        """Interne Methode, die nur zeichnet, wenn ein Container gesetzt wurde."""
        if self.ui_container is not None and st.session_state.log_messages:
            self.ui_container.code("\n".join(st.session_state.log_messages), language="text")

# Wir instanziieren den Logger global. Er ist jetzt von überall erreichbar!
app_logger = LiveLogger()

# set up web page
st.set_page_config(page_title="EAGLE / ISO Mapper", layout="wide")
st.title("🦅 EAGLE ↔️ ISO 19144-2 Mapper")

def clear_logs_and_data():
    st.session_state.log_messages = []
    st.session_state.mapped_data = None
    st.session_state.mapped_filename = None

# --- validation ---

def is_valid_xml(uploaded_file) -> bool:
    try:
        # Da uns XSDs fehlen, prüfen wir zumindest auf Wohlgeformtheit
        app_logger.log("Validating XML...")
        ET.parse(uploaded_file)
        uploaded_file.seek(0) # Pointer zurücksetzen für späteren Read
        return True
    except Exception as e:
        st.error(f"XML Validierungsfehler: {e}")
        return False

def validate_and_get_sheets(uploaded_file) -> Tuple[bool, List[str]]:
    """Prüft die Excel-Datei und gibt eine Liste der CLC-Sheets zurück."""
    app_logger.log("Importing and validating Excel file...")

    try:
        # 1. Sicherstellen, dass wir am Anfang der Datei sind
        uploaded_file.seek(0)

        app_logger.log(f"Loading Workbook...")

        # 2. read_only=True ist hier perfekt, da es extrem schnell ist
        # und nicht den gesamten Speicher volllaufen lässt!
        wb = openpyxl.load_workbook(uploaded_file, read_only=True)

        app_logger.log(f"Extracting sheets...")

        # 3. Filtere direkt die relevanten Sheets
        clc_sheets = [sheet for sheet in wb.sheetnames if sheet.startswith("CLC")]

        # 4. EXTREM WICHTIG: Lesekopf für den Haupt-Parser wieder zurücksetzen!
        uploaded_file.seek(0)

        return True, clc_sheets

    except Exception as e:
        app_logger.log(f"Error reading Workbook: {str(e)}.")
        st.error(f"Error reading Excel file, check if it's a valid .xlsx.\nDetails: {e}")
        # Auch im Fehlerfall sauber zurücksetzen
        uploaded_file.seek(0)
        return False, []

# --- UI TABS ---
tab1, tab2, tab3 = st.tabs(["📊 EAGLE ➔ ISO (Excel to XML)", "📄 ISO ➔ EAGLE (XML to Excel)", "⚙️ Mapping Config"])

# ==========================================
# TAB 1: EAGLE TO ISO
# ==========================================
with tab1:
    st.header("Upload EAGLE Matrix (Excel)")
    uploaded_excel = st.file_uploader("Choose an EAGLE Excel-File",
                                      type=["xlsx"], key="up_excel",
                                      on_change=clear_logs_and_data)

    is_valid = False
    if uploaded_excel is not None:
        is_valid, clc_sheets = validate_and_get_sheets(uploaded_excel)
        if is_valid:
            st.success("File read and validated successfully.")

            try:
                if not clc_sheets:
                    st.warning("no suitable sheets found")
                else:
                    # selection box for sheet to parse
                    st.session_state.selected_sheet = st.selectbox("choose a sheet for mapping", clc_sheets)

            except Exception as e:
                st.error(f"Failed to read Excel file: {e}")

    with st.expander("📜 Show Log", expanded=True):
        log_eagle = st.code("Ready to map...")

    app_logger.set_container(log_eagle)

    if st.button("Map to ISO", disabled=not is_valid, type="primary"):
        try:
            # 3. Erste Live-Nachricht ausgeben
            app_logger.log("Loading EAGLE matrix source file...")

            # Datei laden (dank unserer Seek-Logik sicher)
            wb = openpyxl.load_workbook(uploaded_excel, data_only=True)

            # Execute Mapping, passing the live logging function as a callback
            xml_string_bytes = run_eagle_to_iso_mapping(
                excel_workbook=wb,
                sheet_name=st.session_state.selected_sheet,
                log_callback=app_logger.log
            )

            st.session_state.mapped_data = xml_string_bytes
            st.session_state.mapped_filename = uploaded_excel.name.replace(".xlsx", "_mapped.xml")
            app_logger.log("✅ Mapping completed successfully!")
            st.success("Done!")

        except Exception as e:
            app_logger.log(f"ERROR: {str(e)}")
            st.error("Aborting due to error.")


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
        clear_logs_and_data()
        is_valid = is_valid_xml(uploaded_xml)
        if is_valid:
            st.success("XML is well-formed and valid.")

    with st.expander("📜 Show Log", expanded=True):
        log_iso = st.code("Ready to map...")

    app_logger.set_container(log_iso)

    if st.button("Map to EAGLE", disabled=not is_valid, type="primary"):
        # Übergabe der Checkbox-Werte
        result_bytes = run_iso_to_eagle_mapping(
            uploaded_xml.getvalue(),
            log_callback=app_logger.log,
            use_fuzzy=use_fuzzy,
            force_hierarchical=force_hierarchical
        )

        st.session_state.mapped_data = result_bytes
        st.session_state.mapped_filename = uploaded_xml.name.replace(".xml", "_mapped.xlsx")
        app_logger.log("✅ Mapping successfully completed!")
        st.success("Done!")

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

st.subheader("Export")
if st.session_state.mapped_data is not None:
    mime_type = "application/xml" if st.session_state.mapped_filename.endswith(".xml") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    st.download_button(
        label="⬇️ Download Mapped File",
        data=st.session_state.mapped_data,
        file_name=st.session_state.mapped_filename,
        mime=mime_type,
        type="primary",
        use_container_width=False
    )
else:
    st.info("Download will be available after successful mapping.")