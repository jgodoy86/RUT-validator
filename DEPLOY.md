# Despliegue en servidor Linux privado (red interna / VPN de la empresa)

Esta guía monta el Validador RUT en un servidor Linux accesible **solo desde
la VPN/red privada de la empresa**, nunca desde internet.

## Arquitectura

```
VPN empresa ──▶ [Nginx :443 TLS + Basic Auth] ──▶ (red docker interna) ──▶ [Streamlit :8501]
```

- **Nginx** es el único servicio publicado, y solo en la IP privada del
  servidor (`BIND_IP`), no en `0.0.0.0`.
- **La app Streamlit** corre en un contenedor sin puertos publicados al host;
  solo Nginx puede alcanzarla, a través de la red docker `internal`.
- Los documentos subidos se procesan en memoria y no se guardan en disco
  (confirmado en `rut_validator.py`: todo pasa por `BytesIO`/`Pillow`, sin
  `open()` de escritura ni `NamedTemporaryFile`).

## 1. Requisitos en el servidor

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin ufw
sudo systemctl enable --now docker
```

## 2. Clonar y configurar variables

```bash
git clone https://github.com/jgodoy86/RUT-validator.git
cd RUT-validator
cp .env.example .env
```

Edita `.env`:
- `OPENAI_API_KEY` / `OPENAI_MODEL`: credenciales de OpenAI.
- `BIND_IP`: la IP privada que la VPN de la empresa le asigna a este
  servidor (ej. `10.20.0.5`). **Nunca** dejar `0.0.0.0` en producción.

## 3. Certificado TLS

Como el servidor no es alcanzable desde internet, no aplica el reto HTTP-01
de Let's Encrypt. Dos opciones:

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
  -subj "/CN=validador-rut.interno.empresa.local"
```

Si la empresa tiene un dominio real y control de DNS, también se puede usar
Let's Encrypt con reto **DNS-01** (no requiere puerto 80 abierto) — avísame
si aplica y te dejo esa variante.

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

Verifica: `curl -vk https://<BIND_IP>:443` desde una máquina conectada a la
VPN (debe pedir usuario/clave). Desde fuera de la VPN, la conexión no debe
completar siquiera a nivel de red.

## 6. Firewall: restringir el puerto solo a la VPN

`BIND_IP` ya evita que Docker publique el puerto en todas las interfaces,
pero conviene una segunda capa con `ufw` (defensa en profundidad):

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <RANGO_CIDR_VPN> to any port 443 proto tcp
sudo ufw allow from <RANGO_CIDR_VPN> to any port 22 proto tcp   # SSH también solo por VPN
sudo ufw enable
sudo ufw status verbose
```

Reemplaza `<RANGO_CIDR_VPN>` por el rango real que use la VPN de la empresa
(ej. `10.20.0.0/24`).

> **Nota importante sobre Docker + ufw:** por defecto Docker manipula
> `iptables` directamente y puede publicar puertos saltándose las reglas de
> `ufw` si usas `"443:443"` (equivalente a `0.0.0.0:443:443`). Por eso
> `docker-compose.yml` publica el puerto explícitamente en `${BIND_IP}` y no
> en todas las interfaces — así ni siquiera existe el bind público que
> `ufw` tendría que bloquear.

## 7. Mantenimiento

```bash
docker compose pull        # si usas una imagen publicada, o:
git pull && docker compose up -d --build   # para reconstruir desde el Dockerfile
docker compose logs -f app
docker compose down        # detener
```

## Resumen de capas de seguridad

1. Servidor solo accesible por la VPN de la empresa (red/firewall).
2. `ufw` restringido al CIDR de la VPN (defensa en profundidad).
3. Nginx expuesto solo en la IP privada (`BIND_IP`), nunca `0.0.0.0`.
4. TLS en el reverse proxy (certificado interno o autofirmado).
5. Usuario y clave (Basic Auth) delante de la app.
6. `OPENAI_API_KEY` solo en `.env` (fuera de git) y solo dentro del
   contenedor de la app — Nginx no la ve.
7. Documentos procesados en memoria, sin persistencia en disco.
