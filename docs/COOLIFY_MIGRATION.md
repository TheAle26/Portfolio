# Migración del portfolio a Coolify

Este procedimiento mueve el portfolio a Coolify **en la misma Raspberry**, mantiene PostgreSQL 15 y conserva `vincentalejo.myddns.me`. Los comandos se ejecutan por SSH en la Raspberry, desde el directorio del repositorio actual.

> El respaldo queda en la misma Raspberry. Protege contra un error durante la migración, pero no contra una falla de su disco o tarjeta SD. No borres el stack ni los volúmenes anteriores durante al menos siete días.

## 1. Inventario y respaldo de ensayo

Crear un directorio privado y obtener los nombres reales de los recursos actuales:

```bash
cd /ruta/al/repositorio/Fulbo

COMPOSE_FILE=docker-compose.prod.yml
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=/data/coolify/backups/portfolio-migration/$STAMP

sudo install -d -m 0700 "$BACKUP_DIR"
sudo chown "$(id -u):$(id -g)" "$BACKUP_DIR"

docker compose -f "$COMPOSE_FILE" ps -a > "$BACKUP_DIR/compose-ps.txt"
docker compose -f "$COMPOSE_FILE" config --volumes > "$BACKUP_DIR/compose-volumes.txt"

OLD_DB_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q db)
OLD_WEB_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q web)
OLD_DB_VOLUME=$(docker inspect "$OLD_DB_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')
OLD_MEDIA_VOLUME=$(docker inspect "$OLD_WEB_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}')

test -n "$OLD_DB_CONTAINER" && test -n "$OLD_WEB_CONTAINER"
test -n "$OLD_DB_VOLUME" && test -n "$OLD_MEDIA_VOLUME"
test "$OLD_DB_VOLUME" != "$OLD_MEDIA_VOLUME"

printf 'OLD_DB_CONTAINER=%s\nOLD_WEB_CONTAINER=%s\nOLD_DB_VOLUME=%s\nOLD_MEDIA_VOLUME=%s\n' \
  "$OLD_DB_CONTAINER" "$OLD_WEB_CONTAINER" "$OLD_DB_VOLUME" "$OLD_MEDIA_VOLUME" \
  | tee "$BACKUP_DIR/resources.txt"
```

Guardar una línea base funcional y de datos:

```bash
docker compose -f "$COMPOSE_FILE" exec -T web python manage.py showmigrations --plan \
  > "$BACKUP_DIR/migrations-before.txt"

docker compose -f "$COMPOSE_FILE" exec -T web python manage.py shell -c '
import json
from django.contrib.auth import get_user_model
from apps.orders.models import Pedido
from changomas.models import Product
from tracking.models import DailyReport, Telemetry
print(json.dumps({
    "users": get_user_model().objects.count(),
    "orders": Pedido.objects.count(),
    "products": Product.objects.count(),
    "telemetry": Telemetry.objects.count(),
    "daily_reports": DailyReport.objects.count(),
    "latest_telemetry": str(Telemetry.objects.order_by("-timestamp").values_list("timestamp", flat=True).first()),
}, sort_keys=True))
' > "$BACKUP_DIR/counts-before.json"

docker run --rm -v "$OLD_MEDIA_VOLUME:/media:ro" alpine:3.20 \
  sh -c 'printf "files="; find /media -type f | wc -l; du -sk /media' \
  > "$BACKUP_DIR/media-before.txt"
```

Crear el dump lógico y el archivo de media:

```bash
docker compose -f "$COMPOSE_FILE" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  > "$BACKUP_DIR/portfolio-rehearsal.dump"

docker run --rm -v "$BACKUP_DIR:/backup:ro" postgres:15 \
  pg_restore --list /backup/portfolio-rehearsal.dump \
  > "$BACKUP_DIR/portfolio-rehearsal.list"

docker run --rm \
  -v "$OLD_MEDIA_VOLUME:/source:ro" \
  -v "$BACKUP_DIR:/backup" \
  alpine:3.20 sh -c 'tar -C /source -czf /backup/media-rehearsal.tar.gz .'

cd "$BACKUP_DIR"
sha256sum portfolio-rehearsal.dump media-rehearsal.tar.gz | tee SHA256SUMS.rehearsal
sha256sum -c SHA256SUMS.rehearsal
```

No continuar si algún comando falla, el dump está vacío o `pg_restore --list` no puede leerlo.

## 2. Recursos en Coolify

### PostgreSQL

1. Crear un recurso PostgreSQL con imagen exacta `postgres:15`.
2. Usar los valores actuales de `DB_NAME`, `DB_USER` y `DB_PASSWORD`.
3. Mantenerlo privado: sin port mapping y sin **Make it publicly available**.
4. Iniciarlo y copiar el hostname de su **Internal URL**; ése será `DB_HOST`.
5. Importar `portfolio-rehearsal.dump` desde **Configuration → Import Backup**.

### Aplicación

1. Crear una aplicación desde este repositorio y seleccionar el build pack **Docker Compose**.
2. Usar `/docker-compose.coolify.yml` como Compose Location.
3. Activar **Connect to Predefined Network** en la misma destination que PostgreSQL.
4. Cargar estas variables sin cambiar los secretos actuales:

   - `DJANGO_ENV=production`
   - `SECRET_KEY`
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT=5432`
   - `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
   - `FLESPI_TOKEN`, `GOOGLE_MAPS_API_KEY`
   - `BACKGROUND_PROCESSES_ENABLED=false`

5. Desplegar **sin dominio**. Con el flag en `false`, los tres contenedores de segundo plano permanecen vivos pero no escriben datos.
6. Consultar **Show Deployable Compose** y copiar los identificadores de los contenedores `web` y `frontend-proxy`.

Identificar y cargar el nuevo volumen de media:

```bash
NEW_WEB_CONTAINER='reemplazar-con-id-del-web-de-Coolify'
NEW_PROXY_CONTAINER='reemplazar-con-id-del-frontend-proxy-de-Coolify'
NEW_MEDIA_VOLUME=$(docker inspect "$NEW_WEB_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}')
NEW_APP_UID=$(docker exec "$NEW_WEB_CONTAINER" id -u)
NEW_APP_GID=$(docker exec "$NEW_WEB_CONTAINER" id -g)

test -n "$NEW_MEDIA_VOLUME"
test "$NEW_MEDIA_VOLUME" != "$OLD_MEDIA_VOLUME"

docker run --rm \
  -v "$NEW_MEDIA_VOLUME:/target" \
  -v "$BACKUP_DIR:/backup:ro" \
  alpine:3.20 sh -c "tar -xzf /backup/media-rehearsal.tar.gz -C /target && chown -R $NEW_APP_UID:$NEW_APP_GID /target"
```

Validar el ensayo sin abrir tráfico público:

```bash
docker exec "$NEW_WEB_CONTAINER" python manage.py check --deploy
docker exec "$NEW_WEB_CONTAINER" python manage.py showmigrations --plan
docker exec "$NEW_PROXY_CONTAINER" wget -qO- \
  --header='Host: vincentalejo.myddns.me' \
  --header='X-Forwarded-Proto: https' \
  http://127.0.0.1/ >/dev/null
```

Ejecutar en el `web` nuevo el mismo comando de conteos de la sección anterior y comparar el JSON y las métricas de `media`.

## 3. Corte final

La indisponibilidad comienza al detener los escritores viejos:

Si abriste una sesión SSH nueva, vuelve a definir `COMPOSE_FILE`, `OLD_MEDIA_VOLUME`, `NEW_MEDIA_VOLUME`, `NEW_APP_UID` y `NEW_APP_GID` repitiendo los comandos de descubrimiento anteriores. No escribas nombres de volumen a mano.

```bash
cd /ruta/al/repositorio/Fulbo
docker compose -f "$COMPOSE_FILE" stop web worker scheduler_worker generador_datos

FINAL_STAMP=$(date +%Y%m%d-%H%M%S)
FINAL_DIR=/data/coolify/backups/portfolio-migration/$FINAL_STAMP
sudo install -d -m 0700 "$FINAL_DIR"
sudo chown "$(id -u):$(id -g)" "$FINAL_DIR"

docker compose -f "$COMPOSE_FILE" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  > "$FINAL_DIR/portfolio-final.dump"

docker run --rm -v "$FINAL_DIR:/backup:ro" postgres:15 \
  pg_restore --list /backup/portfolio-final.dump \
  > "$FINAL_DIR/portfolio-final.list"

docker run --rm \
  -v "$OLD_MEDIA_VOLUME:/source:ro" \
  -v "$FINAL_DIR:/backup" \
  alpine:3.20 sh -c 'tar -C /source -czf /backup/media-final.tar.gz .'

cd "$FINAL_DIR"
sha256sum portfolio-final.dump media-final.tar.gz | tee SHA256SUMS.final
sha256sum -c SHA256SUMS.final
```

En Coolify:

1. Detener temporalmente `web` y `frontend-proxy` nuevos.
2. Restaurar `portfolio-final.dump` en PostgreSQL mediante **Import Backup**. Confirmar que el destino mostrado es exclusivamente la base nueva.
3. Reemplazar `media` nuevo, validando otra vez ambos nombres de volumen antes de borrar el destino:

```bash
test -n "$NEW_MEDIA_VOLUME" && test -n "$OLD_MEDIA_VOLUME"
test "$NEW_MEDIA_VOLUME" != "$OLD_MEDIA_VOLUME"

docker run --rm \
  -v "$NEW_MEDIA_VOLUME:/target" \
  -v "$FINAL_DIR:/backup:ro" \
  alpine:3.20 sh -c "
    find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar -xzf /backup/media-final.tar.gz -C /target
    chown -R $NEW_APP_UID:$NEW_APP_GID /target
  "
```

4. Arrancar `web` y `frontend-proxy`; repetir `check --deploy`, conteos, media y la prueba HTTP interna.
5. Cambiar `BACKGROUND_PROCESSES_ENABLED=true` y redeplegar. Verificar en logs una sola instancia de Flespi, scheduler y cada simulador.
6. Detener únicamente el proxy viejo para liberar los puertos públicos:

```bash
cd /ruta/al/repositorio/Fulbo
docker compose -f "$COMPOSE_FILE" stop frontend-proxy
```

7. Iniciar el proxy de Coolify y asignar al servicio `frontend-proxy` el dominio `https://vincentalejo.myddns.me:80`.
8. No modificar No-IP ni el port-forwarding del router: TCP `80/443` debe seguir apuntando a la Raspberry.

## 4. Aceptación y rollback

Comprobar desde fuera de la red:

- certificado TLS y redirección HTTP a HTTPS;
- inicio de sesión, administración y formularios POST/CSRF;
- `/static/`, imágenes y documentos de `/media/`;
- APIs y páginas del comparador;
- timestamps nuevos de telemetría y ejecución programada;
- persistencia tras un redeploy y un reinicio controlado.

Antes de abrir el dominio, el rollback es:

1. Detener la aplicación y el proxy de Coolify.
2. Arrancar el stack anterior, que conserva su volumen original:

```bash
cd /ruta/al/repositorio/Fulbo
docker compose -f docker-compose.prod.yml up -d
```

Después de aceptar escrituras en Coolify, crear primero otro dump de la base nueva antes de cualquier rollback; de otro modo esas escrituras quedarían fuera de la base anterior.

Finalmente, configurar backups programados del PostgreSQL de Coolify, conservar al menos una restauración probada y no eliminar los recursos anteriores durante siete días.
