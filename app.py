import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from rut_validator import validate_rut

load_dotenv()

st.set_page_config(page_title="Validador RUT DIAN", page_icon="✅", layout="wide")


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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", status or "sin estado")
    c2.metric("Coincide", "Sí" if same is True else ("No" if same is False else "No concluyente"))
    c3.metric("Fuente QR", result.get("qr_url_source") or "no detectado")
    c4.metric("Marca de agua", watermark.get("status") or "sin validar")

    if status == "invalid_document":
        st.error(watermark.get("message") or "Documento inválido por marca de agua.")
    elif status == "match":
        st.success("La información verificada coincide con lo recuperado desde el QR.")
    elif status == "different":
        st.error("Hay diferencias entre el documento y la página del QR.")
    else:
        st.warning("No fue posible concluir la comparación con certeza.")

    if result.get("qr_url"):
        st.text_input("URL QR usada", value=result["qr_url"], disabled=True)

    if result.get("notes"):
        for note in result["notes"]:
            st.warning(note)

    doc_fields = (result.get("document_extraction") or {}).get("document_fields") or {}
    page_fields = (result.get("dian_page_extraction") or {}).get("page_fields") or {}
    comparisons = result.get("comparisons") or []

    tab1, tab2, tab3, tab4 = st.tabs(["Comparación", "Documento", "Página DIAN", "JSON"])

    with tab1:
        if comparisons:
            df = pd.DataFrame(comparisons)
            st.dataframe(df, use_container_width=True)
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
        st.code(pretty, language="json")
        st.download_button(
            "Descargar resultado JSON",
            data=pretty.encode("utf-8"),
            file_name="resultado_validacion_rut.json",
            mime="application/json",
        )
