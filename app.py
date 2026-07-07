import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from rut_validator import validate_rut

load_dotenv()

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
    </style>
    """,
    unsafe_allow_html=True,
)


def file_fingerprint(file_bytes: bytes, filename: str) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()
    return f"{filename}:{len(file_bytes)}:{digest}"


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
    st.header("Configuración")
    env_key = os.getenv("OPENAI_API_KEY", "")
    api_key = st.text_input("OpenAI API key", value=env_key, type="password")
    model = st.text_input("Modelo", value=os.getenv("OPENAI_MODEL", "gpt-5.5"))
    prefer_browser = st.checkbox("Abrir DIAN con navegador local (Playwright)", value=True)
    st.markdown("---")
    st.markdown("**Privacidad:** el archivo se procesa en memoria y se envía a OpenAI para extracción estructurada. No se guarda permanentemente por defecto.")

uploaded = st.file_uploader(
    "Sube el RUT en PDF, JPG o PNG",
    type=["pdf", "jpg", "jpeg", "png"],
    key=f"rut_file_{st.session_state['uploader_key']}",
)
manual_qr_url = st.text_area(
    "URL del QR opcional",
    placeholder="Pega aquí la URL de DIAN si ya la tienes o si falla la lectura del QR",
    height=90,
    key=f"manual_qr_{st.session_state['uploader_key']}",
)

file_bytes = uploaded.getvalue() if uploaded else None
filename = uploaded.name if uploaded else None
current_signature = None
if uploaded and file_bytes is not None:
    current_signature = json.dumps(
        {
            "file": file_fingerprint(file_bytes, filename or "rut.pdf"),
            "manual_qr_url": (manual_qr_url or "").strip(),
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
                manual_qr_url=manual_qr_url.strip() or None,
                prefer_browser=prefer_browser,
            )
        except Exception as exc:
            st.session_state["analysis_pending"] = False
            st.session_state["processing_signature"] = None
            st.error(f"Error durante el análisis: {exc}")
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
                comparison_rows.append({
                    "Campo": row.get("field"),
                    "Estado": label,
                    "Documento": format_comparison_value(row.get("document_value")),
                    "QR/DIAN": format_comparison_value(row.get("qr_page_value")),
                })
            comparison_df = pd.DataFrame(comparison_rows)

            def highlight_status(value: str) -> str:
                color_map = {
                    "Coincide": "background-color: #d4edda; color: #155724;",
                    "Diferente": "background-color: #f8d7da; color: #721c24;",
                    "Solo en documento": "background-color: #fff3cd; color: #856404;",
                    "Solo en QR/DIAN": "background-color: #d1ecf1; color: #0c5460;",
                    "Sin dato": "background-color: #e2e3e5; color: #383d41;",
                }
                return color_map.get(value, "")

            styled_df = comparison_df.style.applymap(lambda v: highlight_status(v), subset=["Estado"])
            st.caption("Comparación campo por campo")
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
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
