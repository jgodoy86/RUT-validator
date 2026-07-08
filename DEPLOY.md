# Despliegue en servidor Linux privado (red interna / VPN de la empresa)

Esta guía monta el Validador RUT en un servidor Linux compartido, donde ya
corren otras aplicaciones en producción (portales públicos vía Apache, n8n),
sin tocar nada de lo existente. El validador queda accesible **solo desde
la VPN/red interna de la empresa**, nunca desde internet.

## Arquitectura

```
VPN empresa ──▶ [Nginx :8443 TLS + Basic Auth] ──▶ (red docker interna) ──▶ [Streamlit :8501]
```

- **Nginx** es el único servicio publicado, en el puerto **8443** (no 443:
  en el servidor de referencia, Apache ya ocupa 80/443 sirviendo los
  portales públicos existentes — verifica con `sudo ss -tlnp` antes de
  asumir que un puerto está libre en tu servidor).
- **La app Streamlit** corre en un contenedor sin puertos publicados al host;
  solo Nginx puede alcanzarla, a través de la red docker `internal` — un
  proyecto Compose separado del resto (ver "Aislamiento" abajo).
- Los documentos subidos se procesan en memoria y no se guardan en disco
  (confirmado en `rut_validator.py`: todo pasa por `BytesIO`/`Pillow`, sin
  `open()` de escritura ni `NamedTemporaryFile`).
- El acceso real "solo VPN" depende del **firewall perimetral del proveedor
  de la nube** (no de `ufw`, que suele estar inactivo en estos servidores).
  Antes de terminar, pide al proveedor que abra el puerto 8443 **solo**
  para el rango de la VPN/red interna — el mismo tratamiento que ya deben
  tener otros puertos internos de este servidor.

## Aislamiento de otros proyectos en el mismo servidor

Si el servidor ya tiene otro proyecto Docker Compose corriendo (por ejemplo
n8n en `/home/usrcustomer/docker-compose.yml`), **no lo edites ni lo
reinicies**. Clona este repo en su **propio directorio**
(`/home/usrcustomer/rut-validator/`, o el que uses) — Docker Compose aísla
los proyectos por nombre de directorio, así que `docker compose` aquí no
interferirá con contenedores de otros proyectos siempre que no compartan
puertos ni nombres de red.

Antes de levantar el stack, confirma con `sudo ss -tlnp` qué puertos están
realmente ocupados (no te fíes solo de la documentación del servidor: en
nuestro caso encontramos procesos activos en 80/443 aunque el
`systemd` que se supone los administra estaba en estado `failed`).

## 1. Requisitos en el servidor

Si Docker y Docker Compose ya están instalados (verifica con `docker
--version` y `docker compose version`), sáltate la instalación:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

## 2. Clonar y configurar variables

```bash
mkdir -p ~/rut-validator && cd ~/rut-validator
git clone https://github.com/jgodoy86/RUT-validator.git .
git checkout claude/validador-rut-features-2mv7y8   # hasta que se fusione a main
cp .env.example .env
```

Edita `.env`:
- `OPENAI_API_KEY` / `OPENAI_MODEL`: credenciales de OpenAI.
- `BIND_IP`: déjalo en `0.0.0.0` si el servidor solo tiene una IP (el
  aislamiento real lo da el firewall del proveedor, no el bind local). Si
  el servidor tiene una interfaz separada para la VPN, usa esa IP aquí.

## 3. Certificado TLS

Como el servidor no es alcanzable desde internet en este puerto, no aplica
el reto HTTP-01 de Let's Encrypt (ese sí lo usan los portales públicos vía
Apache/certbot, pero es un caso distinto). Dos opciones:

**a) Certificado de la CA interna de la empresa** (recomendado si existe):
pide a TI un certificado para el nombre/IP interno y colócalo en:
```
deploy/certs/fullchain.pem
deploy/certs/privkey.pem
```

**b) Autofirmado** (rápido para arrancar; el navegador pedirá aceptar la excepción una vez):
```bash
mkdir -p deploy/certs
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout deploy/certs/privkey.pem \
  -out deploy/certs/fullchain.pem \
  -subj "/CN=validador-rut.interno.logicem.local"
```

## 4. Usuario y clave de acceso (segunda capa, además de la VPN)

Con `openssl` (no requiere instalar `apache2-utils`):

```bash
mkdir -p deploy
USUARIO="nombre_gestor"
read -s -p "Clave para $USUARIO: " CLAVE; echo
HASH=$(openssl passwd -apr1 "$CLAVE")
echo "$USUARIO:$HASH" >> deploy/.htpasswd
```

Repite el bloque por cada usuario/gestor que deba tener acceso.

## 5. Levantar la app

```bash
docker compose up -d --build
docker compose logs -f
```

Verifica localmente en el servidor (el certificado autofirmado hará que
`curl` se queje del certificado; `-k` lo ignora solo para esta prueba):
```bash
curl -vk https://localhost:8443
```
Debe responder pidiendo usuario/clave (Basic Auth). Desde una máquina en
la VPN/red interna: `https://10.238.22.169:8443`. Desde fuera de la VPN, la
conexión no debería completar a nivel de red **una vez** que el proveedor
restrinja el puerto (ver siguiente sección) — hasta entonces, pruébalo tú
mismo antes de darlo por controlado.

## 6. Restringir el acceso a la VPN/red interna

En este tipo de servidor, `ufw` normalmente está **inactivo** y el
aislamiento real de puertos "internos" lo aplica el **firewall perimetral
del proveedor de la nube**, no el sistema operativo. Antes de considerar el
despliegue completo:

1. **Pide al proveedor/administrador de la nube privada** que el puerto
   **8443** de este servidor quede abierto **solo** para el rango de la
   VPN/red corporativa — el mismo tratamiento que ya tienen otros puertos
   internos de este servidor (por ejemplo el 3000 de la API interna, o el
   5678 de n8n).
2. **Verifica tú mismo** una vez aplicada la regla: intenta llegar a
   `https://10.238.22.169:8443` desde una red fuera de la VPN (por ejemplo
   datos móviles) — no debería conectar. Y desde la VPN, sí.

No actives `ufw` en este servidor como parte de este despliegue: hacerlo por
primera vez en una máquina con tráfico público en producción (los portales
Laravel) sin catalogar antes cada puerto/servicio activo puede cortar el
SSH o el tráfico público por error. Si más adelante se quiere `ufw` como
capa adicional, se hace aparte, con su propia ventana de mantenimiento y
catalogando primero **todos** los puertos que deben seguir abiertos.

## 7. Mantenimiento

```bash
cd ~/rut-validator
git pull && docker compose up -d --build   # actualizar y reconstruir
docker compose logs -f app
docker compose down        # detener (no afecta a otros proyectos del servidor)
```

## Resumen de capas de seguridad

1. Puerto 8443 (no 80/443, ocupados por Apache) — evita cualquier conflicto
   con los portales públicos existentes.
2. Acceso restringido a la VPN/red interna vía firewall perimetral del
   proveedor de la nube (a gestionar con ellos).
3. Proyecto Docker Compose aislado en su propio directorio — no toca n8n,
   Traefik ni Apache.
4. La app Streamlit no publica puertos al host; solo Nginx es alcanzable.
5. TLS en el reverse proxy (certificado interno o autofirmado).
6. Usuario y clave (Basic Auth) delante de la app.
7. `OPENAI_API_KEY` solo en `.env` (fuera de git) y solo dentro del
   contenedor de la app — Nginx no la ve.
8. Documentos procesados en memoria, sin persistencia en disco.
