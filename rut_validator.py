import base64
import io
import json
import mimetypes
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
    COLOMBIA_TZ: Optional["ZoneInfo"] = ZoneInfo("America/Bogota")
except Exception:
    COLOMBIA_TZ = None

import cv2
import fitz
import numpy as np
import requests
from PIL import Image, ImageDraw

from prompts import DOCUMENT_PROMPT, DIAN_PAGE_PROMPT
from schemas import DOCUMENT_EXTRACTION_SCHEMA, DIAN_PAGE_EXTRACTION_SCHEMA

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DIAN_HOST_SUFFIX = "dian.gov.co"


@dataclass
class DianFetchResult:
    accessible: bool
    method: str
    status_code: Optional[int]
    final_url: Optional[str]
    text: str
    html: str
    screenshot_png: Optional[bytes]
    error: Optional[str] = None


def guess_mime_type(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt:
        return mt
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    return "image/png"


def file_to_data_url(file_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def extract_response_text(response_json: Dict[str, Any]) -> str:
    if isinstance(response_json, dict) and response_json.get("output_text"):
        return response_json["output_text"]
    parts: List[str] = []
    for item in response_json.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict):
                if content.get("text"):
                    parts.append(content["text"])
                elif content.get("type") == "output_text" and content.get("text"):
                    parts.append(content["text"])
    return "\n".join(parts).strip()


def parse_json_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def call_openai_structured(api_key: str, model: str, content: List[Dict[str, Any]], schema_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(OPENAI_RESPONSES_URL, headers=headers, json=payload, timeout=180)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "No se pudo conectar con OpenAI. Revisa conexion a internet, firewall, antivirus, "
            "VPN/proxy o permisos de salida hacia api.openai.com:443. "
            f"Detalle tecnico: {exc}"
        ) from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:2000]}")
    data = resp.json()
    text = extract_response_text(data)
    if not text:
        raise RuntimeError(f"OpenAI no devolvió output_text. Respuesta: {json.dumps(data)[:2000]}")
    return parse_json_text(text)


def render_file_to_images(file_bytes: bytes, filename: str, max_pages: int = 3, zoom: float = 2.5) -> List[Image.Image]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" or guess_mime_type(filename) == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        images: List[Image.Image] = []
        for i in range(min(max_pages, doc.page_count)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        return images
    return [Image.open(io.BytesIO(file_bytes)).convert("RGB")]


def _nit_search_variants(nit: Any) -> List[str]:
    """Variantes de un NIT para localizarlo en el PDF: crudo y con puntos de
    miles (901234567 -> 901.234.567), que es como suele mostrarlo la DIAN."""
    digits = re.sub(r"\D+", "", str(nit or ""))
    if len(digits) < 5:  # muy corto -> ambiguo, no vale la pena buscarlo
        return []
    variants = [digits]
    # Agrupar de a 3 desde la derecha para el formato con puntos.
    rev = digits[::-1]
    dotted = ".".join(rev[i:i + 3] for i in range(0, len(rev), 3))[::-1]
    if dotted != digits:
        variants.append(dotted)
    return variants


def highlight_document_fields(
    file_bytes: bytes, filename: str, document_fields: Dict[str, Any], max_pages: int = 3, zoom: float = 2.5
) -> Optional[List[bytes]]:
    """Resalta en amarillo, sobre el PDF renderizado, los campos que el gestor
    debe revisar: nombre/razón social, NIT, DV y los códigos de responsabilidad.

    Solo funciona con PDFs de texto (los RUT de la DIAN lo son). Para imágenes
    (JPG/PNG) no hay capa de texto y devuelve None. Diseñado para NO resaltar
    nunca de más: si un valor es ambiguo o no se ubica con certeza, se omite.
    """
    is_pdf = Path(filename).suffix.lower() == ".pdf" or guess_mime_type(filename) == "application/pdf"
    if not is_pdf:
        return None
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        return None

    fields = document_fields or {}
    razon = normalize_value(fields.get("razon_social"))
    # Partes del nombre (personas naturales): el nombre compuesto no existe
    # contiguo en el PDF (casillas separadas), así que se resalta cada una.
    name_parts = [
        normalize_value(fields.get(k))
        for k in ("primer_apellido", "segundo_apellido", "primer_nombre", "otros_nombres")
    ]
    name_parts = [p for p in name_parts if p and len(p) >= 3]
    nit_variants = _nit_search_variants(fields.get("nit"))
    dv_value = re.sub(r"\D+", "", str(fields.get("dv") or ""))
    codes = set()
    for item in fields.get("responsabilidades") or []:
        if isinstance(item, dict) and item.get("codigo"):
            c = re.sub(r"\D+", "", str(item.get("codigo")))
            if c:
                codes.add(c.zfill(2))

    YELLOW = (255, 235, 59, 110)
    out: List[bytes] = []
    for i in range(min(max_pages, doc.page_count)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        base = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        def box(x0: float, y0: float, x1: float, y1: float) -> None:
            draw.rectangle([x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom], fill=YELLOW)

        words = page.get_text("words")  # (x0,y0,x1,y1, palabra, block, line, word_no)

        # Razón social (empresa), partes del nombre (persona natural) y NIT: se
        # buscan por su valor exacto y solo se resaltan si aparecen UNA sola vez
        # (inequívoco) para no marcar de más.
        text_needles = [n for n in [razon] if n and len(n) >= 4] + name_parts
        for needle in text_needles:
            rects = page.search_for(needle)
            if len(rects) == 1:
                r = rects[0]
                box(r.x0, r.y0, r.x1, r.y1)
        for needle in nit_variants:
            rects = page.search_for(needle)
            if len(rects) == 1:
                r = rects[0]
                box(r.x0, r.y0, r.x1, r.y1)
                break  # ya ubicado el NIT, no probar más variantes

        # DV: dígito(s) inmediatamente a la derecha de la etiqueta "DV".
        if dv_value:
            for (x0, y0, x1, y1, w, b, l, n) in words:
                if w.rstrip(":.").upper() == "DV":
                    same_line = sorted(
                        [ww for ww in words if ww[5] == b and ww[6] == l and ww[7] > n],
                        key=lambda t: t[7],
                    )
                    if same_line and re.sub(r"\D+", "", same_line[0][4]) == dv_value:
                        nxt = same_line[0]
                        box(nxt[0], nxt[1], nxt[2], nxt[3])
                    break

        # Códigos de responsabilidad: solo tokens que coinciden con un código
        # extraído Y están dentro de la banda de la casilla "Responsabilidades",
        # para no confundirlos con números de dirección/teléfono en otras zonas.
        if codes:
            resp_label_y = None
            for (x0, y0, x1, y1, w, *_rest) in words:
                if "responsabilidad" in w.lower():
                    resp_label_y = y1
                    break
            if resp_label_y is not None:
                for (x0, y0, x1, y1, w, *_rest) in words:
                    if y0 >= resp_label_y and y0 <= resp_label_y + 120 and w.zfill(2) in codes:
                        box(x0, y0, x1, y1)

        merged = Image.alpha_composite(base, overlay).convert("RGB")
        out.append(pil_to_png_bytes(merged))
    return out


def image_bytes_to_pil(file_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(file_bytes)).convert("RGB")


def load_images(file_bytes: bytes, filename: str, max_pages: int = 3) -> List[Image.Image]:
    if guess_mime_type(filename) == "application/pdf" or filename.lower().endswith(".pdf"):
        return render_file_to_images(file_bytes, filename, max_pages=max_pages)
    return [image_bytes_to_pil(file_bytes)]


def decode_qr_from_images(images: List[Image.Image]) -> Optional[str]:
    detector = cv2.QRCodeDetector()
    for img in images:
        rgb = np.array(img.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        variants = [bgr]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        variants.append(gray)
        for scale in [1.5, 2.0, 3.0, 4.0]:
            variants.append(cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))
        for threshold in [cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV]:
            _, th = cv2.threshold(gray, 0, 255, threshold | cv2.THRESH_OTSU)
            variants.append(th)
        for var in variants:
            try:
                data, _, _ = detector.detectAndDecode(var)
                if data:
                    return data.strip()
            except Exception:
                pass
            try:
                ok, decoded, _, _ = detector.detectAndDecodeMulti(var)
                if ok:
                    for d in decoded:
                        if d:
                            return d.strip()
            except Exception:
                pass
    return None


def analyze_document_with_openai(api_key: str, model: str, file_bytes: bytes, filename: str) -> Dict[str, Any]:
    mime_type = guess_mime_type(filename)
    content: List[Dict[str, Any]] = []
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        content.append({
            "type": "input_file",
            "filename": filename or "documento.pdf",
            "file_data": file_to_data_url(file_bytes, "application/pdf"),
            "detail": "high",
        })
        # Enviar también la primera página renderizada como imagen mejora la detección
        # de textos diagonales/marcas de agua que a veces no salen bien del PDF.
        try:
            preview_pages = render_file_to_images(file_bytes, filename, max_pages=1, zoom=2.5)
            if preview_pages:
                content.append({
                    "type": "input_image",
                    "image_url": file_to_data_url(pil_to_png_bytes(preview_pages[0]), "image/png"),
                    "detail": "high",
                })
        except Exception:
            pass
    else:
        content.append({
            "type": "input_image",
            "image_url": file_to_data_url(file_bytes, mime_type),
            "detail": "high",
        })
    content.append({"type": "input_text", "text": DOCUMENT_PROMPT})
    return call_openai_structured(api_key, model, content, "rut_document_extraction", DOCUMENT_EXTRACTION_SCHEMA)


def is_safe_dian_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    is_dian_host = host == DIAN_HOST_SUFFIX or host.endswith(f".{DIAN_HOST_SUFFIX}")
    return parsed.scheme in ("http", "https") and is_dian_host


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_dian_with_requests(url: str) -> DianFetchResult:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
        html = r.text or ""
        text = strip_html(html)
        accessible = r.status_code < 400 and len(text) > 80
        return DianFetchResult(accessible, "requests", r.status_code, r.url, text, html, None, None)
    except Exception as exc:
        return DianFetchResult(False, "requests", None, url, "", "", None, str(exc))


def fetch_dian_with_playwright(url: str) -> DianFetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return DianFetchResult(False, "playwright", None, url, "", "", None, f"Playwright no disponible: {exc}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="es-CO", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            text = page.locator("body").inner_text(timeout=15000)
            html = page.content()
            screenshot = page.screenshot(full_page=True, type="png")
            final_url = page.url
            browser.close()
        accessible = len((text or "").strip()) > 80
        return DianFetchResult(accessible, "playwright", 200, final_url, text or "", html or "", screenshot, None)
    except Exception as exc:
        return DianFetchResult(False, "playwright", None, url, "", "", None, str(exc))


def fetch_dian_page(url: str, prefer_browser: bool = True) -> DianFetchResult:
    if not is_safe_dian_url(url):
        return DianFetchResult(False, "blocked", None, url, "", "", None, "URL no permitida; solo se aceptan dominios dian.gov.co")
    first = fetch_dian_with_playwright(url) if prefer_browser else fetch_dian_with_requests(url)
    if first.accessible and "Procesando" not in first.text[:500]:
        return first
    second = fetch_dian_with_requests(url) if prefer_browser else fetch_dian_with_playwright(url)
    if second.accessible and len(second.text) > len(first.text):
        return second
    return first if len(first.text) >= len(second.text) else second


def analyze_dian_page_with_openai(api_key: str, model: str, fetch: DianFetchResult) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = []
    text = (fetch.text or "").strip()
    if text:
        content.append({"type": "input_text", "text": DIAN_PAGE_PROMPT + "\n\nTexto recuperado de DIAN:\n" + text[:120000]})
    elif fetch.html:
        content.append({"type": "input_text", "text": DIAN_PAGE_PROMPT + "\n\nHTML recuperado de DIAN:\n" + fetch.html[:120000]})
    else:
        content.append({"type": "input_text", "text": DIAN_PAGE_PROMPT + "\n\nNo se recuperó texto útil de la página DIAN."})
    if fetch.screenshot_png:
        content.append({
            "type": "input_image",
            "image_url": file_to_data_url(fetch.screenshot_png, "image/png"),
            "detail": "high",
        })
    return call_openai_structured(api_key, model, content, "dian_page_extraction", DIAN_PAGE_EXTRACTION_SCHEMA)


def normalize_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9@]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def normalize_numeric(value: Any) -> Optional[str]:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    return digits or None


def comparable(field: str, value: Any) -> Optional[str]:
    if field in {"nit", "dv", "telefono_1", "actividad_economica_principal", "numero_formulario"}:
        return normalize_numeric(value)
    return normalize_value(value)


def apply_persona_natural_name(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Para personas naturales la casilla 35 'Razón social' va vacía y el nombre
    está en 31-34. La DIAN, en cambio, muestra el nombre completo como 'Razón
    social'. Si razon_social está vacío pero hay partes del nombre, se compone
    en el mismo orden que usa la DIAN (apellidos + nombres) para que la
    comparación coincida. No pisa una razon_social ya presente (empresas).
    """
    if not isinstance(fields, dict):
        return fields
    if normalize_value(fields.get("razon_social")):
        return fields
    partes = [
        fields.get("primer_apellido"), fields.get("segundo_apellido"),
        fields.get("primer_nombre"), fields.get("otros_nombres"),
    ]
    nombre = " ".join(p.strip() for p in partes if isinstance(p, str) and p.strip())
    if nombre:
        fields["razon_social"] = nombre
    return fields


def compare_simple_fields(document_fields: Dict[str, Any], page_fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = [
        "numero_formulario", "tipo_tramite", "nit", "dv", "direccion_seccional", "tipo_contribuyente",
        "razon_social", "pais", "departamento", "ciudad_municipio", "direccion_principal",
        "correo_electronico", "telefono_1", "actividad_economica_principal", "fecha_inicio_actividad",
        "fecha_generacion_pdf",
    ]
    rows: List[Dict[str, Any]] = []
    for field in fields:
        doc_val = document_fields.get(field)
        page_val = page_fields.get(field)
        doc_cmp = comparable(field, doc_val)
        page_cmp = comparable(field, page_val)
        if doc_cmp and page_cmp:
            status = "match" if doc_cmp == page_cmp else "different"
        elif doc_cmp and not page_cmp:
            status = "only_in_document"
        elif page_cmp and not doc_cmp:
            status = "only_in_qr_page"
        else:
            status = "missing"
        rows.append({
            "field": field,
            "document_value": doc_val,
            "qr_page_value": page_val,
            "status": status,
        })
    return rows


def compare_responsabilidades(document_fields: Dict[str, Any], page_fields: Dict[str, Any]) -> Dict[str, Any]:
    def codes(items: Any) -> set:
        out = set()
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("codigo"):
                    c = normalize_numeric(item.get("codigo"))
                    if c:
                        out.add(c.zfill(2))
        return out
    doc_codes = codes(document_fields.get("responsabilidades"))
    page_codes = codes(page_fields.get("responsabilidades"))
    if doc_codes and page_codes:
        status = "match" if doc_codes == page_codes else "different"
    elif doc_codes and not page_codes:
        status = "only_in_document"
    elif page_codes and not doc_codes:
        status = "only_in_qr_page"
    else:
        status = "missing"
    return {
        "field": "responsabilidades_codigos",
        "document_value": ", ".join(sorted(doc_codes)) if doc_codes else None,
        "qr_page_value": ", ".join(sorted(page_codes)) if page_codes else None,
        "status": status,
    }


def check_obligado_facturar_electronica(document_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Código de responsabilidad 52 = obligado a facturar electrónicamente
    (confirmado con el equipo de Contabilidad, no es una inferencia propia)."""
    codes: set = set()
    items = document_fields.get("responsabilidades")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("codigo"):
                c = normalize_numeric(item.get("codigo"))
                if c:
                    codes.add(c.zfill(2))
    obligado = "52" in codes
    return {
        "obligado": obligado,
        "codigo": "52",
        "message": (
            "El RUT incluye el código de responsabilidad 52: obligado a facturar electrónicamente."
            if obligado
            else "No se encontró el código de responsabilidad 52 en el RUT extraído. "
            "Verifica manualmente si aplica, especialmente si la extracción del documento tuvo advertencias."
        ),
    }


# Formatos observados/esperados para "Fecha de generación documento PDF" en
# el RUT de la DIAN. DD-MM-AAAA es el orden colombiano; se incluyen también
# variantes con "/" y formato AAAA-MM-DD por si acaso, sin asumir uno solo.
_GENERATION_DATE_FORMATS = [
    "%d-%m-%Y %I:%M:%S%p",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %I:%M:%S%p",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def _parse_generation_date(raw: Any) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    # Normaliza variantes de AM/PM ("a.m.", "a. m.", "am" en minúsculas, con
    # o sin espacio) a la forma exacta "AM"/"PM" que espera %p.
    normalized = re.sub(
        r"\s*([AaPp])\.?\s*[Mm]\.?\s*$",
        lambda m: m.group(1).upper() + "M",
        text,
    )
    for fmt in _GENERATION_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def validate_generation_date(document_fields: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Verifica 'fecha_generacion_pdf': no puede ser posterior al momento
    actual (imposible en un documento legítimo -> fuerte señal de
    adulteración) ni de un año distinto al actual (política de vigencia).

    Principio de diseño: si la fecha no se pudo extraer o interpretar, NO se
    marca como inválida (evita falsos positivos); solo se avisa que no se
    pudo verificar.
    """
    raw = document_fields.get("fecha_generacion_pdf")
    if now is None:
        now = datetime.now(COLOMBIA_TZ) if COLOMBIA_TZ else datetime.utcnow()
    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now

    if not raw:
        return {
            "field": "fecha_generacion_pdf", "document_value": None, "status": "missing",
            "is_invalid": False,
            "message": "No se extrajo la fecha de generación del documento.",
        }
    parsed = _parse_generation_date(raw)
    if parsed is None:
        return {
            "field": "fecha_generacion_pdf", "document_value": raw, "status": "unparseable",
            "is_invalid": False,
            "message": f"No se pudo interpretar la fecha de generación ({raw!r}); revísala manualmente.",
        }
    if parsed > now_naive:
        return {
            "field": "fecha_generacion_pdf", "document_value": raw, "status": "future_date",
            "is_invalid": True,
            "message": (
                f"La fecha de generación ({raw}) es POSTERIOR a la fecha/hora actual "
                f"({now_naive.strftime('%d-%m-%Y %H:%M:%S')}). Esto es imposible en un "
                "documento legítimo y es una señal fuerte de adulteración."
            ),
        }
    if parsed.year != now_naive.year:
        return {
            "field": "fecha_generacion_pdf", "document_value": raw, "status": "wrong_year",
            "is_invalid": True,
            "message": (
                f"La fecha de generación ({raw}) no corresponde al año en curso "
                f"({now_naive.year}); el documento no está vigente, solicita uno actualizado."
            ),
        }
    return {
        "field": "fecha_generacion_pdf", "document_value": raw, "status": "ok",
        "is_invalid": False,
        "message": "La fecha de generación es coherente con la fecha y el año actuales.",
    }


def build_generation_date_comparison(validation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "field": "fecha_generacion_documento",
        "document_value": validation.get("document_value"),
        "qr_page_value": None,
        "status": validation.get("status"),
        "message": validation.get("message"),
    }


def normalize_watermark_text(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def validate_document_watermark(document_fields: Dict[str, Any]) -> Dict[str, Any]:
    marcas = document_fields.get("marcas_agua") or []
    if isinstance(marcas, str):
        marcas = [marcas]
    normalized = normalize_watermark_text(marcas)

    # Para este validador, la palabra clave crítica es BORRADOR.
    # "SIN COSTO" por sí sola no invalida; combinada con BORRADOR confirma que no es documento final.
    is_draft = "BORRADOR" in normalized
    has_watermark = bool(normalized)

    if is_draft:
        status = "invalid_draft_watermark"
        message = "El documento contiene marca de agua de BORRADOR; no debe aprobarse como RUT final/definitivo."
    elif has_watermark:
        status = "watermark_detected_review"
        message = "Se detectó una marca de agua o leyenda. Revísala manualmente si no corresponde a un RUT final."
    else:
        status = "not_detected"
        message = "No se detectó marca de agua visible. Si esperabas validar una leyenda específica, revisa la calidad del archivo."

    return {
        "field": "marcas_agua",
        "document_value": marcas if marcas else None,
        "status": status,
        "is_draft": is_draft,
        "message": message,
    }


def build_watermark_comparison(watermark_validation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "field": "marca_agua_documento",
        "document_value": watermark_validation.get("document_value"),
        "qr_page_value": None,
        "status": watermark_validation.get("status"),
        "message": watermark_validation.get("message"),
    }


def build_qr_page_comparison(qr_page_loaded: bool, qr_url: Optional[str]) -> Dict[str, Any]:
    if qr_page_loaded:
        return {
            "field": "consulta_qr_dian",
            "document_value": qr_url,
            "qr_page_value": "La pagina DIAN cargo informacion util del RUT.",
            "status": "match",
            "message": "El QR abre una consulta DIAN con informacion verificable.",
        }
    return {
        "field": "consulta_qr_dian",
        "document_value": qr_url,
        "qr_page_value": "La pagina DIAN no cargo informacion util del RUT.",
        "status": "invalid_qr_page",
        "message": "El QR fue detectado, pero no abre una pagina DIAN con informacion verificable. Marca el documento como posible no original o adulterado.",
    }


def compare_results(document_extraction: Dict[str, Any], page_extraction: Dict[str, Any], qr_page_loaded: bool, qr_url: Optional[str]) -> Dict[str, Any]:
    doc_fields = document_extraction.get("document_fields") or {}
    page_fields = page_extraction.get("page_fields") or {}
    watermark_validation = validate_document_watermark(doc_fields)
    generation_date_validation = validate_generation_date(doc_fields)
    comparisons = compare_simple_fields(doc_fields, page_fields)
    comparisons.append(compare_responsabilidades(doc_fields, page_fields))
    comparisons.append(build_watermark_comparison(watermark_validation))
    comparisons.append(build_generation_date_comparison(generation_date_validation))
    comparisons.append(build_qr_page_comparison(qr_page_loaded, qr_url))
    differences = [r for r in comparisons if r["status"] in {"different", "invalid_qr_page"}]
    matches = [r for r in comparisons if r["status"] == "match"]
    invalid_draft = bool(watermark_validation.get("is_draft"))
    invalid_generation_date = bool(generation_date_validation.get("is_invalid"))
    invalid_qr_page = not qr_page_loaded

    if invalid_draft:
        verification_status = "invalid_document"
        same_information = False
    elif invalid_generation_date:
        verification_status = "invalid_document"
        same_information = False
    elif invalid_qr_page:
        verification_status = "invalid_document"
        same_information = False
    elif differences:
        verification_status = "different"
        same_information = False
    elif matches and not differences:
        verification_status = "match"
        same_information = True
    else:
        verification_status = "inconclusive"
        same_information = None
    return {
        "ok": True,
        "verification_status": verification_status,
        "same_information": same_information,
        "document_watermark_validation": watermark_validation,
        "document_generation_date_validation": generation_date_validation,
        "comparisons": comparisons,
        "match_count": len(matches),
        "difference_count": len(differences),
    }


def validate_rut(api_key: str, model: str, file_bytes: bytes, filename: str, prefer_browser: bool = True) -> Dict[str, Any]:
    images = load_images(file_bytes, filename, max_pages=3)
    # Previsualización del documento (para la vista comparada en la UI). Se
    # renderiza una sola vez y se transporta como PNG en bytes; app.py lo
    # excluye del JSON descargable porque no es serializable.
    document_pages_png = [pil_to_png_bytes(img) for img in images]
    qr_url_local = decode_qr_from_images(images)
    document_extraction = analyze_document_with_openai(api_key, model, file_bytes, filename)
    doc_fields = document_extraction.get("document_fields") or {}
    # Personas naturales: componer razon_social desde las casillas de nombre
    # (31-34) para poder compararla contra el nombre que muestra la DIAN.
    apply_persona_natural_name(doc_fields)
    watermark_validation = validate_document_watermark(doc_fields)
    qr_url_ai = document_extraction.get("qr_url_detected_by_ai")
    qr_url = (qr_url_local or qr_url_ai or "").strip() or None
    # Resaltado de los campos a revisar (nombre, NIT, DV, códigos) sobre el PDF.
    # Devuelve None para imágenes (sin capa de texto); si algo falla, no bloquea
    # el análisis: simplemente no habrá versión resaltada.
    try:
        document_pages_highlighted_png = highlight_document_fields(file_bytes, filename, doc_fields)
    except Exception:
        document_pages_highlighted_png = None
    result: Dict[str, Any] = {
        "ok": True,
        "filename": filename,
        "qr_url": qr_url,
        "qr_url_source": "local_opencv" if qr_url_local else ("openai" if qr_url_ai else None),
        "qr_url_local_opencv": qr_url_local,
        "qr_url_detected_by_ai": qr_url_ai,
        "document_extraction": document_extraction,
        "obligado_facturar_electronica": check_obligado_facturar_electronica(doc_fields),
        "previews": {
            "document_pages_png": document_pages_png,
            "document_pages_highlighted_png": document_pages_highlighted_png,
            "dian_screenshot_png": None,
        },
    }
    if not qr_url:
        generation_date_validation = validate_generation_date(doc_fields)
        invalid_draft = bool(watermark_validation.get("is_draft"))
        invalid_generation_date = bool(generation_date_validation.get("is_invalid"))
        invalid_document = invalid_draft or invalid_generation_date
        # Sin QR no hay con qué comparar en DIAN, pero igual se muestran todos
        # los campos ya extraídos del documento (compare_simple_fields con
        # page_fields vacío marca cada uno como "only_in_document").
        doc_only_comparisons = compare_simple_fields(doc_fields, {})
        doc_only_comparisons.append(compare_responsabilidades(doc_fields, {}))
        doc_only_comparisons.append(build_watermark_comparison(watermark_validation))
        doc_only_comparisons.append(build_generation_date_comparison(generation_date_validation))
        result.update({
            "qr_page_accessible": False,
            "verification_status": "invalid_document" if invalid_document else "qr_unavailable",
            "same_information": False if invalid_document else None,
            "dian_page_extraction": None,
            "document_watermark_validation": watermark_validation,
            "document_generation_date_validation": generation_date_validation,
            "comparisons": doc_only_comparisons,
            "match_count": 0,
            "difference_count": 0,
            "notes": [
                "No se pudo decodificar el QR ni consultar DIAN. Se muestran los campos "
                "extraídos del documento sin comparar contra la página oficial; revisa "
                "manualmente contra la DIAN si necesitas certeza total."
            ],
        })
        if invalid_generation_date:
            result["notes"].insert(0, generation_date_validation.get("message") or "Fecha de generación inválida.")
        if invalid_draft:
            result["notes"].insert(0, watermark_validation.get("message") or "Documento con marca de agua de borrador.")
        return result
    fetch = fetch_dian_page(qr_url, prefer_browser=prefer_browser)
    result["previews"]["dian_screenshot_png"] = fetch.screenshot_png
    result["dian_fetch"] = {
        "accessible": fetch.accessible,
        "method": fetch.method,
        "status_code": fetch.status_code,
        "final_url": fetch.final_url,
        "error": fetch.error,
        "text_excerpt": (fetch.text or "")[:1000],
        "has_screenshot": bool(fetch.screenshot_png),
    }
    page_extraction = analyze_dian_page_with_openai(api_key, model, fetch)
    # Por consistencia: si la DIAN llegara a devolver el nombre en casillas
    # separadas en vez de razon_social, se compone igual.
    apply_persona_natural_name(page_extraction.get("page_fields") or {})
    qr_page_loaded = bool(fetch.accessible and page_extraction.get("page_loaded"))
    comparison = compare_results(document_extraction, page_extraction, qr_page_loaded, qr_url)
    result.update(comparison)
    result["qr_page_accessible"] = qr_page_loaded
    result["dian_page_extraction"] = page_extraction
    notes: List[str] = []
    watermark_validation = result.get("document_watermark_validation") or {}
    generation_date_validation = result.get("document_generation_date_validation") or {}
    if watermark_validation.get("is_draft"):
        notes.append(watermark_validation.get("message") or "Documento con marca de agua de borrador.")
    if generation_date_validation.get("is_invalid"):
        notes.append(generation_date_validation.get("message") or "Fecha de generación inválida.")
    if fetch.error:
        notes.append(f"DIAN fetch error: {fetch.error}")
    if not qr_page_loaded:
        notes.append("El QR fue detectado, pero DIAN no cargo informacion util del RUT. El documento se marca como posible no original o adulterado.")
    result["notes"] = notes
    return result
