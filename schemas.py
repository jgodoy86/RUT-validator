DOCUMENT_FIELDS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "numero_formulario", "tipo_tramite", "nit", "dv", "direccion_seccional",
        "tipo_contribuyente", "razon_social", "pais", "departamento", "ciudad_municipio",
        "direccion_principal", "correo_electronico", "telefono_1",
        "actividad_economica_principal", "fecha_inicio_actividad", "fecha_generacion_pdf",
        "responsabilidades", "marcas_agua"
    ],
    "properties": {
        "numero_formulario": {"type": ["string", "null"]},
        "tipo_tramite": {"type": ["string", "null"]},
        "nit": {"type": ["string", "null"]},
        "dv": {"type": ["string", "null"]},
        "direccion_seccional": {"type": ["string", "null"]},
        "tipo_contribuyente": {"type": ["string", "null"]},
        "razon_social": {"type": ["string", "null"]},
        "pais": {"type": ["string", "null"]},
        "departamento": {"type": ["string", "null"]},
        "ciudad_municipio": {"type": ["string", "null"]},
        "direccion_principal": {"type": ["string", "null"]},
        "correo_electronico": {"type": ["string", "null"]},
        "telefono_1": {"type": ["string", "null"]},
        "actividad_economica_principal": {"type": ["string", "null"]},
        "fecha_inicio_actividad": {"type": ["string", "null"]},
        "fecha_generacion_pdf": {"type": ["string", "null"]},
        "responsabilidades": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["codigo", "descripcion"],
                "properties": {
                    "codigo": {"type": ["string", "null"]},
                    "descripcion": {"type": ["string", "null"]}
                }
            }
        },
        "marcas_agua": {"type": "array", "items": {"type": "string"}}
    }
}

DOCUMENT_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok", "source_type", "qr_url_detected_by_ai", "document_fields", "warnings"],
    "properties": {
        "ok": {"type": "boolean"},
        "source_type": {"type": ["string", "null"]},
        "qr_url_detected_by_ai": {"type": ["string", "null"]},
        "document_fields": DOCUMENT_FIELDS_SCHEMA,
        "warnings": {"type": "array", "items": {"type": "string"}}
    }
}

DIAN_PAGE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok", "page_loaded", "page_fields", "source_text_excerpt", "warnings"],
    "properties": {
        "ok": {"type": "boolean"},
        "page_loaded": {"type": "boolean"},
        "page_fields": DOCUMENT_FIELDS_SCHEMA,
        "source_text_excerpt": {"type": ["string", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}}
    }
}
