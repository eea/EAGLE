import streamlit as st
import io
import time
from typing import Tuple, List
import openpyxl
import xml.etree.ElementTree as ET
import yaml

from src.config import settings
from src.mapping.eagle_to_iso import run_eagle_to_iso_mapping
from src.mapping.iso_to_eagle import run_iso_to_eagle_mapping

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

# --- CSS Tuning: hide Streamlit UI ---
hide_st_style = """
<style>
/* Versteckt den kompletten Header (inkl. Menü und Standard-Lade-Indikator) */
header {visibility: hidden;}

/* Versteckt den Streamlit Footer ("Made with Streamlit") */
footer {visibility: hidden;}

/* Reduziert den riesigen weißen Leerraum oben und unten */
.block-container {
    padding-top: 0rem !important; 
    padding-bottom: 1rem !important;
}
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Splash
# Wir prüfen, ob die App in dieser Session schon fertig geladen hat
if "app_ready" not in st.session_state:

    # 1. Wir reservieren den gesamten Bildschirm mit einem Platzhalter
    splash_placeholder = st.empty()

    # 2. Wir zeichnen den Splash-Screen in diesen Platzhalter
    with splash_placeholder.container():
        # Ein bisschen Luft nach oben
        st.markdown("<div style='margin-top: 15vh;'></div>", unsafe_allow_html=True)

        # 1. Logo zentriert anzeigen
        # 'use_container_width=False' erlaubt dir, die Pixelbreite zu steuern,
        # damit das Logo nicht den ganzen Bildschirm sprengt.
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # Hier den Pfad zu deinem Logo (PNG/JPG/SVG)
            st.image("images/project-logo_small.webp", use_container_width=False, width=200)
        # 2. Text darunter
        st.markdown("<h2 style='text-align: center; color: #333;'>LChS Transformation Engine</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #888;'>Initialisiere Systemressourcen...</p>", unsafe_allow_html=True)

        with col2:
            st.progress(100)

        time.sleep(0.6)  # Display splash screen briefly during first startup

        # 4. DIE MAGIE: Wir leeren den Platzhalter.
        # Der Splash-Screen verschwindet sofort, OHNE dass die Seite neu lädt!
        splash_placeholder.empty()

    # Wir merken uns, dass wir fertig sind, damit der Splash bei Button-Klicks nicht wiederkommt
    st.session_state.app_ready = True

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

        # 3. Filtere gezielt Sheets, die tatsächlich EAGLE Barcoding-Daten enthalten (erkennbar an 'Class Code')
        clc_sheets = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            has_class_code = False
            for row in ws.iter_rows(max_row=8, max_col=6, values_only=True):
                if any("Class Code" in str(cell or '') for cell in row):
                    has_class_code = True
                    break
            if has_class_code:
                clc_sheets.append(sheet_name)

        if not clc_sheets:
            # Fallback falls anders strukturiert
            clc_sheets = [s for s in wb.sheetnames if s.startswith("CLC")] or list(wb.sheetnames)
        else:
            # Bevorzuge Multiklassen- oder CLC-Sheets ganz oben im Dropdown
            clc_sheets.sort(key=lambda s: (0 if "all" in s.lower() else (1 if s.startswith("CLC") else 2)))

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
tab1, tab2, tab3 = st.tabs(["📊 EAGLE ➔ ISO (Excel to XML)", "📄 ISO ➔ EAGLE (XML to Excel)", "⚙️ Mapping & Schema Config"])

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
            # Erste Live-Nachricht ausgeben
            app_logger.log("Loading EAGLE matrix source file...")

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
# TAB 3: ADMIN (SSSOM & LinkML Viewer)
# ==========================================
with tab3:
    st.subheader("SSSOM Crosswalk Mapping (eagle_iso_sssom.yaml)")
    st.markdown("Semantic mappings between EAGLE and ISO 19144 (LCML/LUML).")

    # Show SSSOM table summary
    try:
        from src.mapping.sssom_engine import sssom_resolver
        if sssom_resolver.msdf is not None and not sssom_resolver.msdf.df.empty:
            summary_cols = ["subject_id", "subject_label", "predicate_id", "object_id", "object_label"]
            available_cols = [c for c in summary_cols if c in sssom_resolver.msdf.df.columns]
            st.dataframe(sssom_resolver.msdf.df[available_cols], use_container_width=True, height=260)
    except Exception as e:
        st.warning(f"Could not render SSSOM summary table: {e}")

    # SSSOM Raw YAML editor
    import yaml
    if settings.SSSOM_CONFIG_PATH.exists():
        with open(settings.SSSOM_CONFIG_PATH, "r", encoding="utf-8") as f:
            current_yaml = f.read()
    else:
        current_yaml = ""

    new_yaml = st.text_area("Edit SSSOM YAML", value=current_yaml, height=300)

    if st.button("Save SSSOM Crosswalk"):
        try:
            yaml.safe_load(new_yaml)
            with open(settings.SSSOM_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(new_yaml)
            sssom_resolver.load()
            st.success("SSSOM crosswalk updated and reloaded successfully!")
        except Exception as e:
            st.error(f"Error saving SSSOM YAML: {e}")

    st.divider()

    # LinkML Model viewer
    st.subheader("LinkML Model (eagle-iso-mapping.linkml.yaml)")
    if settings.LINKML_MODEL_PATH.exists():
        with open(settings.LINKML_MODEL_PATH, "r", encoding="utf-8") as g:
            linkml_yaml = g.read()
    else:
        linkml_yaml = "LinkML model file not found."

    st.code(linkml_yaml, language="yaml", height=250)

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