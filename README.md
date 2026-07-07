# Validador local de RUT DIAN por QR

Aplicación local con interfaz web para cargar un PDF/imagen de RUT, leer el QR, abrir la consulta de DIAN/MUISCA y comparar la información visible del documento contra la página del QR.

## Arquitectura

1. **Streamlit** muestra la interfaz local.
2. **OpenCV + PyMuPDF** renderizan PDF/imagen y decodifican el QR localmente.
3. **OpenAI Responses API** extrae campos visibles del RUT y de la captura/página DIAN en JSON estructurado.
4. **Requests/Playwright** intentan abrir la URL de DIAN. Playwright permite cargar páginas con JavaScript y tomar screenshot.
5. El sistema compara campo por campo y devuelve un JSON descargable.

## Instalación local

```bash
cd rut-validator-local
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py
```

Luego abre la URL que te muestra Streamlit, normalmente:

```text
http://localhost:8501
```

## Configurar API key

Puedes pegar la API key en la barra lateral de la app, o crear un archivo `.env` así:

```bash
cp .env.example .env
```

Y editar:

```text
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
```

## Flujo de uso

1. Carga el PDF o imagen del RUT.
2. Revisa si el sistema decodificó la URL del QR.
3. Si no decodifica, pega manualmente la URL del QR en el campo opcional.
4. Haz clic en **Analizar y comparar**.
5. Descarga el resultado JSON.

## Migración a servidor privado

Este proyecto ya incluye `Dockerfile`. Para montar en un servidor privado:

```bash
docker build -t rut-validator-local .
docker run -p 8501:8501 --env-file .env rut-validator-local
```

En producción considera agregar autenticación, HTTPS y políticas de retención de archivos. Por defecto esta app no guarda documentos cargados en disco de forma permanente.

## Limitaciones

- DIAN/MUISCA puede bloquear automatización, exigir cookies, JavaScript o CAPTCHA. En ese caso el resultado puede ser `inconclusive`.
- La lectura de QR depende de la nitidez del documento. Si falla, pega la URL manualmente.
- El análisis con OpenAI se envía a la API; no uses documentos sensibles si no tienes autorización del titular.

## Validación de marca de agua

La app valida el campo `document_fields.marcas_agua`. Si detecta una leyenda con la palabra `BORRADOR`, por ejemplo `DOCUMENTO BORRADOR SIN COSTO`, el resultado queda como:

```json
{
  "verification_status": "invalid_document",
  "same_information": false,
  "document_watermark_validation": {
    "status": "invalid_draft_watermark",
    "is_draft": true
  }
}
```

Esto se evalúa como validación del documento, no como comparación contra la página DIAN, porque la página del QR normalmente no trae la marca de agua del PDF.

## Versión v3 - ajustes de interfaz

Esta versión agrega:

- Carpeta `.streamlit/config.toml` para reducir la barra superior de Streamlit y ocultar opciones como Deploy.
- Botón `Limpiar / subir otro documento`.
- El botón `Analizar y comparar` se deshabilita después de analizar el mismo archivo con la misma configuración.
- Para volver a analizar, cambia el archivo, cambia la URL QR manual, cambia el modelo/configuración o usa `Limpiar / subir otro documento`.

Si la app está corriendo, detén con `Ctrl + C` y vuelve a ejecutar:

```powershell
streamlit run app.py
```

## v4 - Ajuste de flujo de verificación

- Al iniciar la verificación, el botón principal cambia a `Verificación en curso...` y queda deshabilitado.
- Cuando termina la validación del mismo documento, el botón `Analizar y comparar` se oculta.
- Para iniciar otro proceso se usa `Limpiar / subir otro documento`.
