# Instrucciones para agentes IA

Este proyecto es una app local en Streamlit para validar documentos RUT de Colombia.

## Objetivo del proyecto

La aplicación permite cargar un RUT en PDF, JPG o PNG, extraer información visible del documento, leer el QR, consultar la página DIAN/MUISCA asociada y comparar ambos resultados.

## Reglas generales

- No modificar lógica crítica sin explicar antes el cambio.
- No eliminar validaciones de seguridad.
- No guardar archivos subidos permanentemente salvo que se solicite.
- No exponer, imprimir ni subir la variable `OPENAI_API_KEY`.
- No poner API keys directamente en el código fuente.
- Mantener separación de responsabilidades:
  - `app.py`: interfaz Streamlit.
  - `rut_validator.py`: lógica de validación.
  - `schemas.py`: esquemas JSON.
  - `prompts.py`: prompts de OpenAI.
  - `.streamlit/config.toml`: configuración visual de Streamlit.

## Flujo esperado de la app

1. El usuario sube PDF, JPG o PNG.
2. La app decodifica el QR localmente con OpenCV.
3. La app detecta marca de agua.
4. Si detecta `DOCUMENTO BORRADOR SIN COSTO`, debe marcar el documento como inválido.
5. La app usa OpenAI para extraer campos visibles del RUT.
6. La app intenta abrir la página DIAN con Playwright.
7. La app compara documento contra página DIAN.
8. Después de analizar, el botón `Analizar y comparar` debe ocultarse o quedar deshabilitado.
9. Para iniciar otro análisis, el usuario debe usar `Limpiar / subir otro documento`.

## Reglas de interfaz

- No mostrar el botón Deploy de Streamlit.
- No permitir doble análisis del mismo archivo sin limpiar.
- Mostrar claramente:
  - estado de validación,
  - si coincide o no,
  - fuente del QR,
  - estado de marca de agua,
  - URL QR usada,
  - comparación campo por campo.

## Antes de modificar código

- Revisar primero `app.py` y `rut_validator.py`.
- Explicar qué archivo se va a modificar.
- Hacer cambios pequeños y verificables.
- No ejecutar comandos destructivos.
- No instalar paquetes nuevos sin justificarlo.

## Comandos seguros

```powershell
streamlit run app.py
python --version
pip install -r requirements.txt
python -m playwright install chromium
```
