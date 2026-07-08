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
        padding-top: 1.75rem;
    }
    /* El título de Streamlit trae un line-height ajustado que recorta las
       letras (se ve "mocho"); le damos aire arriba y abajo. */
    div[data-testid="stMainBlockContainer"] h1 {
        line-height: 1.2;
        padding-top: 0.25rem;
        padding-bottom: 0.5rem;
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
    st.session_state["batch_results"] = {}
    st.session_state["batch_pending"] = False


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


def show_analysis_error(exc_or_message: Any) -> None:
    message = exc_or_message if isinstance(exc_or_message, str) else str(exc_or_message)
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


MAX_FILES = 5

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "batch_results" not in st.session_state:
    # signature -> {"filename": str, "result": dict | None, "error": str | None}
    st.session_state["batch_results"] = {}
if "batch_pending" not in st.session_state:
    st.session_state["batch_pending"] = False

st.title("Validador RUT DIAN")
st.caption(
    f"Carga hasta {MAX_FILES} PDF o imágenes de RUT, decodifica el QR, "
    "consulta DIAN/MUISCA y compara los campos de cada uno."
)

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
        f"""
        <div class="upload-section-title">Carga de documentos</div>
        <div class="upload-section-copy">
            Arrastra hasta {MAX_FILES} PDF o imágenes de RUT hasta el area punteada azul,
            o usa el boton central para buscarlos en tu equipo.
            Formatos permitidos: PDF, JPG o PNG. Tamano maximo: 10 MB por archivo.
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded_files = st.file_uploader(
        "Arrastra o selecciona uno o varios documentos RUT",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key=f"rut_files_{st.session_state['uploader_key']}",
        label_visibility="collapsed",
    )

if uploaded_files and len(uploaded_files) > MAX_FILES:
    st.warning(
        f"Se permiten máximo {MAX_FILES} documentos a la vez. "
        f"Se usarán solo los primeros {MAX_FILES} de los {len(uploaded_files)} que subiste."
    )
    uploaded_files = uploaded_files[:MAX_FILES]

# Cada item representa un archivo cargado con su "firma" (huella del contenido +
# configuración). La firma es la llave para no reprocesar un archivo ya analizado
# ni perder su resultado cuando Streamlit vuelve a ejecutar el script.
items: list[dict] = []
for uf in uploaded_files or []:
    file_bytes = uf.getvalue()
    oversized = uf.size > 10 * 1024 * 1024
    signature = None
    if not oversized:
        signature = json.dumps(
            {
                "file": file_fingerprint(file_bytes, uf.name),
                "model": (model or "").strip(),
                "prefer_browser": bool(prefer_browser),
            },
            sort_keys=True,
        )
    items.append({
        "filename": uf.name,
        "size": uf.size,
        "file_bytes": file_bytes,
        "oversized": oversized,
        "signature": signature,
    })

for it in items:
    if it["oversized"]:
        st.error(f"'{it['filename']}' excede el límite de 10 MB y no se incluirá en el análisis.")

valid_items = [it for it in items if not it["oversized"]]
pending_items = [it for it in valid_items if it["signature"] not in st.session_state["batch_results"]]

button_col1, button_col2 = st.columns([1, 1])
with button_col1:
    if st.session_state["batch_pending"]:
        st.button("Verificación en curso...", type="primary", disabled=True)
    else:
        label = "Analizar y comparar" if len(valid_items) <= 1 else f"Analizar {len(pending_items)} documento(s)"
        run_clicked = st.button(
            label,
            type="primary",
            disabled=not pending_items or not api_key,
        )
        if run_clicked:
            st.session_state["batch_pending"] = True
            st.rerun()

with button_col2:
    clear = st.button(
        "Limpiar / subir otro documento",
        disabled=not items and not st.session_state["batch_results"],
    )

if clear:
    reset_upload_state()
    st.rerun()

completed_items = [it for it in valid_items if it["signature"] in st.session_state["batch_results"]]

if clear:
    reset_upload_state()
    st.rerun()
elif not items and not api_key:
    st.info("Sube uno o varios PDF/JPG/PNG y pega tu OpenAI API key para iniciar la validación.")
elif not items:
    st.info(f"Sube hasta {MAX_FILES} PDF, JPG o PNG para iniciar la validación.")
elif not api_key:
    st.warning("Pega tu OpenAI API key para habilitar el análisis.")
elif st.session_state["batch_pending"]:
    st.info("La verificación ya inició. Espera a que termine.")
elif pending_items:
    st.info(f"{len(pending_items)} documento(s) listo(s). Haz clic en **Analizar** para procesarlos.")
elif completed_items:
    st.info("Todos los documentos cargados ya fueron analizados. Para empezar de nuevo usa **Limpiar / subir otro documento**.")

if st.session_state["batch_pending"]:
    remaining = [it for it in valid_items if it["signature"] not in st.session_state["batch_results"]]
    if not remaining:
        st.session_state["batch_pending"] = False
    else:
        total = len(remaining)
        progress = st.progress(0.0, text=f"Analizando 1/{total}: {remaining[0]['filename']}...")
        for i, it in enumerate(remaining, start=1):
            progress.progress((i - 1) / total, text=f"Analizando {i}/{total}: {it['filename']}...")
            try:
                result = validate_rut(
                    api_key=api_key.strip(),
                    model=model.strip(),
                    file_bytes=it["file_bytes"],
                    filename=it["filename"],
                    prefer_browser=True,
                )
                st.session_state["batch_results"][it["signature"]] = {
                    "filename": it["filename"], "result": result, "error": None,
                }
            except Exception as exc:
                st.session_state["batch_results"][it["signature"]] = {
                    "filename": it["filename"], "result": None, "error": str(exc),
                }
            progress.progress(i / total)
        st.session_state["batch_pending"] = False
        st.rerun()


def render_result(result: dict, key_prefix: str) -> None:
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

    obligado_fe = result.get("obligado_facturar_electronica") or {}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Estado", title)
    c2.metric("Coincide", "Sí" if same is True else ("No" if same is False else "No concluyente"))
    c3.metric("Fuente QR", result.get("qr_url_source") or "no detectado")
    c4.metric("Marca de agua", watermark.get("status") or "sin validar")
    c5.metric(
        "Factura electrónica",
        "Obligado (cód. 52)" if obligado_fe.get("obligado") else "No registra cód. 52",
        help=obligado_fe.get("message"),
    )

    if result.get("qr_url"):
        st.text_input("URL QR usada", value=result["qr_url"], disabled=True, key=f"qrurl_{key_prefix}")

    if result.get("notes"):
        notes_html = "<strong>Notas</strong><br>" + "<br>".join(f"• {note}" for note in result["notes"])
        st.markdown(f'<div class="notes-box">{notes_html}</div>', unsafe_allow_html=True)

    doc_fields = (result.get("document_extraction") or {}).get("document_fields") or {}
    page_fields = (result.get("dian_page_extraction") or {}).get("page_fields") or {}
    comparisons = result.get("comparisons") or []
    previews = result.get("previews") or {}
    document_pages_png = previews.get("document_pages_png") or []
    dian_screenshot_png = previews.get("dian_screenshot_png")

    tab_preview, tab1, tab2, tab3, tab4 = st.tabs(
        ["Vista comparada", "Comparación", "Documento", "Página DIAN", "JSON"]
    )

    with tab_preview:
        st.caption(
            "Compara el documento cargado (izquierda) con la página de DIAN abierta "
            "desde el QR (derecha). Pasa el cursor sobre cada imagen y usa el icono de "
            "ampliar (⛶) en la esquina para verla a pantalla completa y leerla mejor."
        )
        col_doc, col_dian = st.columns(2)
        with col_doc:
            st.markdown("**📄 Documento cargado**")
            if document_pages_png:
                for i, png in enumerate(document_pages_png):
                    caption = f"Página {i + 1}" if len(document_pages_png) > 1 else None
                    st.image(png, use_container_width=True, caption=caption)
            else:
                st.info("No hay previsualización del documento.")
        with col_dian:
            st.markdown("**🔎 Página DIAN (captura del QR)**")
            if dian_screenshot_png:
                st.image(dian_screenshot_png, use_container_width=True)
            else:
                st.info(
                    "No se capturó la página DIAN. Puede que el QR no estuviera "
                    "disponible o que DIAN no cargara la información."
                )

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
        # "previews" lleva imágenes en bytes (no serializables) y pesaría de más
        # en el JSON; se excluye del resultado descargable.
        serializable = {k: v for k, v in result.items() if k != "previews"}
        pretty = json.dumps(serializable, ensure_ascii=False, indent=2)
        with st.expander("Ver JSON completo", expanded=False):
            st.code(pretty, language="json")
        st.download_button(
            "Descargar resultado JSON",
            data=pretty.encode("utf-8"),
            file_name=f"resultado_validacion_rut_{key_prefix}.json",
            mime="application/json",
            key=f"download_{key_prefix}",
        )


def outer_tab_label(filename: str, entry: dict) -> str:
    if entry.get("error"):
        icon = "❌"
    else:
        result = entry.get("result") or {}
        title, _, _ = status_label_for_verification(
            result.get("verification_status"), result.get("same_information")
        )
        icon = title.split(" ", 1)[0]
    short_name = filename if len(filename) <= 22 else filename[:19] + "..."
    return f"{icon} {short_name}"


if completed_items:
    # El script del botón de copiar se inyecta una sola vez: instala un
    # listener delegado sobre el documento padre, así que no hace falta
    # repetirlo por cada documento/pestaña.
    components.html(COPY_BUTTON_SCRIPT, height=0)

    if len(completed_items) == 1:
        it = completed_items[0]
        entry = st.session_state["batch_results"][it["signature"]]
        if entry["error"]:
            show_analysis_error(entry["error"])
        else:
            render_result(entry["result"], key_prefix="unico")
    else:
        outer_labels = [
            outer_tab_label(it["filename"], st.session_state["batch_results"][it["signature"]])
            for it in completed_items
        ]
        outer_tabs = st.tabs(outer_labels)
        for idx, (outer_tab, it) in enumerate(zip(outer_tabs, completed_items), start=1):
            with outer_tab:
                entry = st.session_state["batch_results"][it["signature"]]
                st.caption(f"📄 {it['filename']}")
                if entry["error"]:
                    show_analysis_error(entry["error"])
                else:
                    render_result(entry["result"], key_prefix=f"doc{idx}")
