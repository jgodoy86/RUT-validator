import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from rut_validator import validate_rut

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path, override=True)

st.set_page_config(page_title="Validador RUT DIAN", page_icon="✅", layout="wide")
st.markdown(
    """
    <style>
    div[data-testid="stMainBlockContainer"] {
        padding-top: 0.5rem;
    }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 0.75rem;
        padding: 0.75rem 0.9rem;
    }
    .result-banner {
        background: linear-gradient(90deg, #f8fafc 0%, #ffffff 100%);
        border: 1px solid #e5e7eb;
        border-left: 5px solid #2563eb;
        border-radius: 0.85rem;
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
    }
    .result-banner-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .result-banner-subtitle {
        color: #475467;
        font-size: 0.95rem;
    }
    .notes-box {
        background: #fffbeb;
        border: 1px solid #fcd34d;
        border-left: 4px solid #f59e0b;
        border-radius: 0.65rem;
        padding: 0.75rem 0.9rem;
        margin-top: 0.75rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: 2px dashed #7dd3fc;
        border-radius: 1rem;
        background: #f0f9ff;
        padding: 1rem 1.05rem 1.1rem;
        box-shadow: none;
    }
    .upload-section-title {
        color: #075985;
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
    }
    .upload-section-copy {
        color: #334155;
        font-size: 0.92rem;
        margin-bottom: 0.95rem;
    }
    .uploaded-file-card {
        align-items: center;
        background: #ffffff;
        border: 1px solid #bae6fd;
        border-radius: 0.85rem;
        display: flex;
        gap: 0.8rem;
        justify-content: flex-start;
        margin-top: 0.55rem;
        min-height: 3.5rem;
        padding: 0.65rem 0.8rem;
        text-align: left;
    }
    .uploaded-file-icon {
        align-items: center;
        background: #e0f2fe;
        border-radius: 0.65rem;
        color: #075985;
        display: flex;
        font-size: 1.2rem;
        height: 2.35rem;
        justify-content: center;
        width: 2.35rem;
    }
    .uploaded-file-name {
        color: #0f172a;
        font-weight: 700;
        line-height: 1.2;
        max-width: min(36rem, 70vw);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .uploaded-file-meta {
        color: #64748b;
        font-size: 0.86rem;
        margin-top: 0.15rem;
    }
    .remove-upload-button button {
        align-items: center !important;
        border: 1px solid #bae6fd !important;
        border-radius: 999px !important;
        color: #075985 !important;
        display: inline-flex !important;
        font-size: 1.15rem !important;
        height: 2.25rem !important;
        justify-content: center !important;
        margin-top: 1rem !important;
        min-width: 2.25rem !important;
        padding: 0 !important;
        width: 2.25rem !important;
    }
    div[data-testid="stFileUploader"] {
        margin-top: 0.35rem;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {
        align-items: center;
        background: #ffffff !important;
        border: 2px dashed #38bdf8 !important;
        border-radius: 0.9rem !important;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        justify-content: center;
        min-height: 118px;
        padding: 1.35rem 1rem !important;
        text-align: center;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] div[data-testid="stFileUploaderFile"] {
        display: none !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
        display: none !important;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] > div {
        align-items: center;
        display: flex;
        flex-direction: column;
        gap: 0.55rem;
        justify-content: center;
        width: 100%;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {
        border-color: #38bdf8 !important;
        color: #075985 !important;
        display: inline-flex !important;
        font-size: 0 !important;
        justify-content: center !important;
        margin: 0 auto !important;
        min-width: 11rem;
        text-align: center !important;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button * {
        display: none !important;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button::after {
        content: "Seleccionar archivo";
        font-size: 0.95rem;
        font-weight: 600;
    }
    div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] small {
        color: #64748b !important;
        display: block !important;
        margin: 0 !important;
        text-align: center !important;
        width: 100% !important;
    }
    div[data-testid="stFileUploader"] .css-1vvy4qg {
        margin-top: 0.5rem !important;
    }
    div[data-testid="stTextArea"] textarea {
        border-radius: 0.75rem;
    }
    div[data-testid="stButton"] button[kind="secondary"] {
        border-color: #bae6fd;
        color: #075985;
    }
    .copy-cell {
        align-items: center;
        display: flex;
        gap: 0.5rem;
        justify-content: space-between;
    }
    .copy-cell-value {
        min-width: 0;
        overflow-wrap: anywhere;
    }
    button.copy-btn {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 0.45rem;
        cursor: pointer;
        flex-shrink: 0;
        font-size: 0.85rem;
        line-height: 1;
        padding: 0.2rem 0.35rem;
    }
    button.copy-btn:hover {
        background: #e0f2fe;
        border-color: #38bdf8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def file_fingerprint(file_bytes: bytes, filename: str) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()
    return f"{filename}:{len(file_bytes)}:{digest}"


def format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


def file_type_label(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return (suffix or "file").upper()[:4]


def get_env_path() -> Path:
    return Path(__file__).resolve().parent / ".env"


def find_logo_path() -> Optional[Path]:
    for filename in ("logo.png", "logo.jpg", "logo.jpeg", "logo.svg"):
        candidate = Path(__file__).resolve().parent / "assets" / filename
        if candidate.exists():
            return candidate
    return None


def set_env_variable(key: str, value: str) -> None:
    env_path = get_env_path()
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    safe_value = value.replace('"', '\\"')
    if " " in safe_value or "#" in safe_value:
        safe_value = f'"{safe_value}"'
    updated = False
    output_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            output_lines.append(f"{key}={safe_value}")
            updated = True
        else:
            output_lines.append(line)
    if not updated:
        output_lines.append(f"{key}={safe_value}")
    env_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def check_openai_connection(api_key: str) -> Tuple[bool, str]:
    if not api_key.strip():
        return False, "No hay API key configurada."
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=15,
        )
    except requests.exceptions.RequestException as exc:
        return (
            False,
            "Python/Streamlit no pudo abrir conexion HTTPS hacia api.openai.com:443. "
            f"Detalle: {exc}",
        )
    if response.status_code == 200:
        return True, "Conexion con OpenAI correcta desde esta instancia de Streamlit."
    if response.status_code == 401:
        return False, "OpenAI respondio 401: la API key no es valida, no esta activa o no se esta leyendo correctamente."
    return False, f"OpenAI respondio HTTP {response.status_code}: {response.text[:300]}"


def reset_upload_state():
    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
    st.session_state["last_result"] = None
    st.session_state["last_signature"] = None
    st.session_state["last_filename"] = None
    st.session_state["analysis_pending"] = False
    st.session_state["processing_signature"] = None


def status_label_for_verification(status: Optional[str], same: Any) -> Tuple[str, str, str]:
    if status == "invalid_document":
        return "❌ Documento inválido", "error", "El documento fue marcado como inválido por la marca de agua o por la comparación."
    if status == "match":
        return "✅ Coincide", "success", "La información del documento y la página DIAN coincide."
    if status == "different":
        return "⚠️ Diferencias detectadas", "warning", "Se encontraron diferencias entre el documento y la página DIAN."
    if status == "qr_unavailable":
        return "🔎 QR no disponible", "info", "No fue posible obtener una URL del QR para consultar DIAN."
    return "❓ Sin conclusión", "info", "No fue posible concluir la comparación con certeza."


def comparison_status_label(status: Optional[str]) -> Tuple[str, str]:
    mapping = {
        "match": ("Coincide", "#2e7d32"),
        "different": ("Diferente", "#c62828"),
        "invalid_qr_page": ("QR/DIAN inválido", "#c62828"),
        "only_in_document": ("Solo en documento", "#ef6c00"),
        "only_in_qr_page": ("Solo en QR/DIAN", "#1565c0"),
        "missing": ("Sin dato", "#6c757d"),
    }
    return mapping.get(status or "", ("Sin dato", "#6c757d"))


def format_comparison_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def show_analysis_error(exc: Exception) -> None:
    message = str(exc)
    network_markers = [
        "api.openai.com",
        "HTTPSConnectionPool",
        "WinError 10013",
        "No se pudo conectar con OpenAI",
        "Failed to establish a new connection",
    ]
    if any(marker in message for marker in network_markers):
        st.error("No se pudo conectar con OpenAI.")
        st.warning(
            "El documento no fallo. Windows o la red bloquearon la salida hacia "
            "`api.openai.com:443`. Revisa firewall, antivirus, VPN/proxy, permisos "
            "de la terminal o politica de red."
        )
        with st.expander("Detalle tecnico", expanded=False):
            st.code(message)
        return
    st.error(f"Error durante el analisis: {message}")


# st.markdown no ejecuta manejadores onclick (React los descarta), por eso el botón
# solo lleva data-copy y este script — inyectado en un iframe con components.html —
# instala un único listener delegado sobre el documento padre.
COPY_BUTTON_SCRIPT = """
<script>
(function () {
    const doc = window.parent.document;
    if (doc.__rutCopyDelegated) { return; }
    doc.__rutCopyDelegated = true;
    doc.addEventListener("click", function (event) {
        const btn = event.target && event.target.closest ? event.target.closest("button.copy-btn") : null;
        if (!btn) { return; }
        const value = btn.getAttribute("data-copy") || "";
        const done = function () {
            btn.textContent = "✔";
            setTimeout(function () { btn.textContent = "📋"; }, 1200);
        };
        const fallback = function () {
            const area = doc.createElement("textarea");
            area.value = value;
            area.style.position = "fixed";
            area.style.opacity = "0";
            doc.body.appendChild(area);
            area.focus();
            area.select();
            try { doc.execCommand("copy"); } catch (err) {}
            doc.body.removeChild(area);
            done();
        };
        const clipboard = window.parent.navigator.clipboard;
        if (clipboard && window.parent.isSecureContext) {
            clipboard.writeText(value).then(done, fallback);
        } else {
            fallback();
        }
    }, true);
})();
</script>
"""


def copy_button_html(escaped_value: str) -> str:
    """Botón de copiar para un valor ya escapado con html.escape (sin botón si no hay dato)."""
    if not escaped_value or escaped_value == "—":
        return ""
    return (
        f'<button type="button" class="copy-btn" data-copy="{escaped_value}" '
        'title="Copiar al portapapeles">📋</button>'
    )


def copy_cell_html(escaped_value: str) -> str:
    button = copy_button_html(escaped_value)
    if not button:
        return escaped_value
    return (
        "<span class='copy-cell'>"
        f"<span class='copy-cell-value'>{escaped_value}</span>{button}"
        "</span>"
    )


def build_comparison_table_html(rows: list[dict]) -> str:
    header = (
        "<tr>"
        "<th>Campo</th>"
        "<th>Estado</th>"
        "<th>Documento</th>"
        "<th>QR/DIAN</th>"
        "</tr>"
    )
    body = []
    for row in rows:
        doc_value = html.escape(str(row["Documento"]))
        page_value = html.escape(str(row["QR/DIAN"]))
        status = row["Estado"]
        colors = {
            "✅ Coincide": "#d4edda",
            "❌ Diferente": "#f8d7da",
            "⚠️ Solo en documento": "#fff3cd",
            "ℹ️ Solo en QR/DIAN": "#d1ecf1",
            "— Sin dato": "#e2e3e5",
        }
        background = colors.get(status, "#f8fafc")
        if row.get("RawStatus") == "invalid_qr_page":
            background = "#f8d7da"
            status = "QR/DIAN invalido"
        if row["Campo"] == "marca_agua_documento":
            normalized_doc = html.unescape(doc_value).upper()
            if "BORRADOR" in normalized_doc:
                background = "#f8d7da"
                status = "❌ Borrador"
            elif "CERTIFICADO" in normalized_doc or "SIN COSTO" in normalized_doc:
                background = "#d4edda"
                status = "✅ Válido"
            else:
                background = "#f8d7da"
                status = "❌ Texto inválido"
        body.append(
            "<tr>"
            f"<td style='padding:0.6rem 0.75rem; border-bottom:1px solid #e5e7eb;'>{html.escape(row['Campo'])}</td>"
            f"<td style='padding:0.6rem 0.75rem; background:{background}; border-radius:0.65rem; white-space:nowrap;'>{status}</td>"
            f"<td style='padding:0.6rem 0.75rem; border-bottom:1px solid #e5e7eb;'>{copy_cell_html(doc_value)}</td>"
            f"<td style='padding:0.6rem 0.75rem; border-bottom:1px solid #e5e7eb;'>{copy_cell_html(page_value)}</td>"
            "</tr>"
        )
    return (
        "<div style='overflow-x:auto;'>"
        "<table style='width:100%; border-collapse:separate; border-spacing:0 0.4rem;'>"
        f"{header}{''.join(body)}"
        "</table>"
        "</div>"
    )


if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "last_signature" not in st.session_state:
    st.session_state["last_signature"] = None
if "last_filename" not in st.session_state:
    st.session_state["last_filename"] = None
if "analysis_pending" not in st.session_state:
    st.session_state["analysis_pending"] = False
if "processing_signature" not in st.session_state:
    st.session_state["processing_signature"] = None

st.title("Validador local de RUT DIAN por QR")
st.caption("Carga un PDF o imagen del RUT, decodifica el QR, consulta DIAN/MUISCA y compara los campos.")

with st.sidebar:
        logo_path = find_logo_path()
        if logo_path:
            st.image(str(logo_path), width=180)
        st.header("Configuración")
        saved_key = os.getenv("OPENAI_API_KEY", "").strip()
        if saved_key:
            # Ya hay clave configurada. Por seguridad NO la mostramos ni la
            # cargamos al navegador (un campo password igual expone el valor en
            # el DOM). Solo estado + opción de reemplazarla. El botón "Guardar"
            # no se muestra mientras exista una clave.
            api_key = saved_key
            st.success("🔑 API key configurada")
            st.caption(
                "Por seguridad, la clave guardada no se muestra. Para cambiarla, "
                "elimínala y guarda una nueva."
            )
            if st.button("Eliminar API key", type="secondary"):
                try:
                    set_env_variable("OPENAI_API_KEY", "")
                    load_dotenv(get_env_path(), override=True)
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo eliminar la API key: {exc}")
        else:
            # No hay clave: primera vez (o tras eliminar). Se muestra el campo
            # y el botón Guardar. El campo arranca vacío, nunca precargado.
            api_key = st.text_input("OpenAI API key", value="", type="password").strip()
            if st.button("Guardar API key", disabled=not api_key):
                try:
                    set_env_variable("OPENAI_API_KEY", api_key)
                    load_dotenv(get_env_path(), override=True)
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la API key: {exc}")
        model = st.text_input("Modelo", value=os.getenv("OPENAI_MODEL", "gpt-5.5"))
        # La página DIAN suele necesitar JavaScript, así que siempre se intenta
        # primero con el navegador local (Playwright) y requests queda como
        # respaldo automático. Es un detalle técnico, no una opción de usuario.
        prefer_browser = True
        if st.button("Probar conexión OpenAI", disabled=not api_key):
            ok, message = check_openai_connection(api_key)
            if ok:
                st.success(message)
            else:
                st.error(message)
        st.markdown("---")
        st.markdown("**Privacidad:** el archivo se procesa en memoria y se envía a OpenAI para extracción estructurada. No se guarda permanentemente por defecto.")

with st.container(border=True):
    st.markdown(
        """
        <div class="upload-section-title">Carga del documento</div>
        <div class="upload-section-copy">
            Arrastra el PDF o imagen del RUT hasta el area punteada azul.
            Tambien puedes usar el boton central para buscarlo en tu equipo.
            Formatos permitidos: PDF, JPG o PNG. Tamano maximo: 10 MB.
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Arrastra o selecciona el documento RUT",
        type=["pdf", "jpg", "jpeg", "png"],
        key=f"rut_file_{st.session_state['uploader_key']}",
        label_visibility="collapsed",
    )
    if uploaded:
        st.markdown(
            """
            <style>
            div[data-testid="stFileUploader"] {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        file_col, remove_col = st.columns([0.94, 0.06])
        with file_col:
            st.markdown(
                f"""
                <div class="uploaded-file-card">
                    <div class="uploaded-file-icon">{file_type_label(uploaded.name)}</div>
                    <div>
                        <div class="uploaded-file-name">{html.escape(uploaded.name)}</div>
                        <div class="uploaded-file-meta">{format_file_size(uploaded.size)} cargado correctamente</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with remove_col:
            st.markdown('<div class="remove-upload-button">', unsafe_allow_html=True)
            remove_uploaded = st.button("X", key=f"remove_uploaded_{st.session_state['uploader_key']}", help="Eliminar archivo")
            st.markdown("</div>", unsafe_allow_html=True)
        if remove_uploaded:
            reset_upload_state()
            st.rerun()
file_bytes = uploaded.getvalue() if uploaded else None
filename = uploaded.name if uploaded else None
if uploaded and uploaded.size > 10 * 1024 * 1024:
    st.error("El archivo excede el límite de 10 MB. Selecciona un archivo más pequeño.")
    uploaded = None
    file_bytes = None
    filename = None
    current_signature = None
else:
    current_signature = None
    if uploaded and file_bytes is not None:
        current_signature = json.dumps(
            {
                "file": file_fingerprint(file_bytes, filename or "rut.pdf"),
                "model": (model or "").strip(),
                "prefer_browser": bool(prefer_browser),
            },
            sort_keys=True,
        )

# Si el usuario cambia archivo/configuración después de un análisis, desbloqueamos el flujo.
# Importante: no cancelar analysis_pending cuando acabamos de hacer clic en
# "Analizar y comparar". En ese momento last_signature todavía es None o anterior,
# pero processing_signature ya corresponde al documento actual y debe continuar.
if (
    current_signature
    and current_signature != st.session_state.get("last_signature")
    and current_signature != st.session_state.get("processing_signature")
):
    st.session_state["analysis_pending"] = False
    st.session_state["processing_signature"] = None

already_analyzed = bool(
    uploaded
    and st.session_state.get("last_result") is not None
    and current_signature == st.session_state.get("last_signature")
)

is_processing = bool(
    uploaded
    and st.session_state.get("analysis_pending") is True
    and current_signature == st.session_state.get("processing_signature")
)

button_col1, button_col2 = st.columns([1, 1])
with button_col1:
    if is_processing:
        st.button("Verificación en curso...", type="primary", disabled=True)
    elif already_analyzed:
        # Después de analizar, ocultamos el botón principal para evitar reprocesar el mismo documento.
        st.empty()
    else:
        run_clicked = st.button(
            "Analizar y comparar",
            type="primary",
            disabled=uploaded is None or not api_key,
        )
        if run_clicked:
            st.session_state["analysis_pending"] = True
            st.session_state["processing_signature"] = current_signature
            st.rerun()

with button_col2:
    clear = st.button(
        "Limpiar / subir otro documento",
        disabled=uploaded is None and st.session_state.get("last_result") is None,
    )

if clear:
    reset_upload_state()
    st.rerun()

if uploaded and not api_key:
    st.warning("Pega tu OpenAI API key para habilitar el análisis.")
elif is_processing:
    st.info("La verificación ya inició. Espera a que termine o usa **Limpiar / subir otro documento** para cancelar visualmente y empezar de nuevo.")
elif uploaded and already_analyzed:
    st.info("Este documento ya fue analizado. Para iniciar un proceso nuevo, usa **Limpiar / subir otro documento**.")
elif uploaded:
    st.info("Archivo cargado. Haz clic en **Analizar y comparar**.")
else:
    st.info("Sube un PDF, JPG o PNG para iniciar la validación.")

if is_processing:
    with st.spinner("Analizando documento, leyendo QR y consultando DIAN..."):
        try:
            result = validate_rut(
                api_key=api_key.strip(),
                model=model.strip(),
                file_bytes=file_bytes,
                filename=filename or "rut.pdf",
                prefer_browser=prefer_browser,
            )
        except Exception as exc:
            st.session_state["analysis_pending"] = False
            st.session_state["processing_signature"] = None
            show_analysis_error(exc)
            st.stop()

    st.session_state["last_result"] = result
    st.session_state["last_signature"] = current_signature
    st.session_state["last_filename"] = filename
    st.session_state["analysis_pending"] = False
    st.session_state["processing_signature"] = None
    st.rerun()

result_to_show = None
if uploaded and st.session_state.get("last_result") is not None and current_signature == st.session_state.get("last_signature"):
    result_to_show = st.session_state["last_result"]

if result_to_show:
    result = result_to_show
    status = result.get("verification_status")
    same = result.get("same_information")

    watermark = result.get("document_watermark_validation") or {}
    title, banner_type, detail_message = status_label_for_verification(status, same)

    status_color = {
        "error": "#b42318",
        "success": "#027a48",
        "warning": "#b54708",
        "info": "#175cd3",
    }.get(banner_type, "#175cd3")

    st.markdown(
        f"""
        <div class="result-banner" style="border-left: 5px solid {status_color};">
            <div class="result-banner-title">{title}</div>
            <div class="result-banner-subtitle">{detail_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if banner_type == "error":
        st.error(watermark.get("message") or "Documento inválido por marca de agua.")
    elif banner_type == "success":
        st.success("La información verificada coincide con lo recuperado desde el QR.")
    elif banner_type == "warning":
        st.warning("Hay diferencias entre el documento y la página del QR.")
    else:
        st.info("No fue posible concluir la comparación con certeza.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", title)
    c2.metric("Coincide", "Sí" if same is True else ("No" if same is False else "No concluyente"))
    c3.metric("Fuente QR", result.get("qr_url_source") or "no detectado")
    c4.metric("Marca de agua", watermark.get("status") or "sin validar")

    if result.get("qr_url"):
        st.text_input("URL QR usada", value=result["qr_url"], disabled=True)

    if result.get("notes"):
        notes_html = "<strong>Notas</strong><br>" + "<br>".join(f"• {note}" for note in result["notes"])
        st.markdown(f'<div class="notes-box">{notes_html}</div>', unsafe_allow_html=True)

    doc_fields = (result.get("document_extraction") or {}).get("document_fields") or {}
    page_fields = (result.get("dian_page_extraction") or {}).get("page_fields") or {}
    comparisons = result.get("comparisons") or []

    tab1, tab2, tab3, tab4 = st.tabs(["Comparación", "Documento", "Página DIAN", "JSON"])

    with tab1:
        if comparisons:
            comparison_rows = []
            for row in comparisons:
                label, _ = comparison_status_label(row.get("status"))
                emoji_status = {
                    "Coincide": "✅ Coincide",
                    "Diferente": "❌ Diferente",
                    "Solo en documento": "⚠️ Solo en documento",
                    "Solo en QR/DIAN": "ℹ️ Solo en QR/DIAN",
                    "Sin dato": "— Sin dato",
                }.get(label, label)
                comparison_rows.append({
                    "Campo": row.get("field"),
                    "Estado": emoji_status,
                    "RawStatus": row.get("status"),
                    "Documento": format_comparison_value(row.get("document_value")),
                    "QR/DIAN": format_comparison_value(row.get("qr_page_value")),
                })

            table_html = build_comparison_table_html(comparison_rows)
            st.caption("Comparación campo por campo")
            st.markdown(table_html, unsafe_allow_html=True)
            components.html(COPY_BUTTON_SCRIPT, height=0)
        else:
            st.info("No hay comparación disponible.")

    with tab2:
        st.subheader("Validación de marca de agua")
        st.json(result.get("document_watermark_validation") or {})
        st.subheader("Campos extraídos del documento")
        st.json(doc_fields)
        warnings = (result.get("document_extraction") or {}).get("warnings") or []
        if warnings:
            st.write("Advertencias:")
            for w in warnings:
                st.write(f"- {w}")

    with tab3:
        st.subheader("Campos extraídos desde DIAN/MUISCA")
        st.json(page_fields)
        st.subheader("Detalle técnico de consulta")
        st.json(result.get("dian_fetch") or {})

    with tab4:
        pretty = json.dumps(result, ensure_ascii=False, indent=2)
        with st.expander("Ver JSON completo", expanded=False):
            st.code(pretty, language="json")
        st.download_button(
            "Descargar resultado JSON",
            data=pretty.encode("utf-8"),
            file_name="resultado_validacion_rut.json",
            mime="application/json",
        )
