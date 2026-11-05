# Supermarket Tracker

## Comportamiento

La entrada pública es `/supermarket-tracker/`. Los enlaces de `/changomas/` redirigen conservando consultas y fichas; los POST usan 307 para conservar método y cuerpo. La API v1 mantiene su contrato; v2 agrega catálogo agrupado y cotización con cantidades en `/api/v2/supermarkets/products/` y `/api/v2/supermarkets/quote/`.

El catálogo es público. El carrito de invitado queda en el dispositivo; las cuentas conservan su propio carrito en la base. Importar un carrito local requiere pulsar Importar; un ID de lote evita sumarlo otra vez si se reintenta. Las cantidades se actualizan con una versión para detectar conflictos entre dispositivos. Hay un máximo de 60 líneas, 99 unidades por línea y 100 seguimientos por cuenta.

Las identidades canónicas usan GTIN con dígito verificador válido. Cada cadena conserva sus publicaciones y referencias. Las publicaciones sin código pueden guardarse y cotizarse mediante un identificador de ficha. No se sustituyen productos por similitud de nombre.

Las cotizaciones aplican grupos completos de promociones por cantidad; las unidades restantes llevan precio base. Las condiciones restringidas o no interpretables no reducen el total. No se incluyen envío, beneficios bancarios personales ni checkout. Los datos de más de 36 horas quedan fuera de recomendaciones actuales; el historial diario conserva 30 días.

## Actualizaciones y alertas

- Catálogos completos: 03:00, hora de Argentina.
- Productos seguidos: cada seis horas, a las 00:20, 06:20, 12:20 y 18:20.
- Despacho del outbox: cada minuto.
- Las corridas usan leases por cadena y muestran su estado en administración.
- Una ausencia o error de respuesta no produce un precio ficticio ni una alerta.
- Un seguimiento evalúa las publicaciones del mismo producto. Cada alerta explica supermercado, condición y precio.
- El objetivo compara el precio de una unidad. Las promociones por cantidad muestran sus requisitos.
- Una promoción sin cambios no se vuelve a enviar. Un objetivo se rearma después de observar un precio superior.
- Se exige verificar el email y habilitar las notificaciones. Cambiar de email invalida la coincidencia de verificación.
- Cada correo incluye una baja con confirmación por POST. Los enlaces de verificación vencen en 24 horas; los de baja en 30 días.
- Antes del envío se vuelve a comprobar el consentimiento y los seguimientos activos.
- Un fallo SMTP temporal confirmado se reintenta hasta cinco veces. Un resultado incierto queda para revisión y no se reenvía automáticamente. La aceptación SMTP no garantiza entrega al buzón.

## Despliegue gradual

1. Respaldar PostgreSQL con el procedimiento habitual y conservar la imagen anterior. Revisar la migración aditiva y sus índices; el backfill de identidades puede tardar según el catálogo.
2. Ejecutar la suite PostgreSQL de CI y `python manage.py makemigrations --check --dry-run`.
3. Mantener `BACKGROUND_PROCESSES_ENABLED=false` durante el ensayo de Coolify. Aplicar `python manage.py migrate` y `python manage.py collectstatic --noinput` antes de levantar web/scheduler nuevos.
4. Verificar catálogo, registro, carrito privado, importación, seguimientos y las redirecciones con una cuenta de prueba. Validar fuentes por separado con `python manage.py scrape_supermarkets --store jumbo --max-categories 1`; las corridas parciales no disparan alertas.
5. Configurar `SUPERMARKET_PUBLIC_URL=https://vincentalejo.myddns.me/supermarket-tracker/`, SMTP existente y `DEFAULT_FROM_EMAIL`. El timeout SMTP es de 15 segundos.
6. Habilitar los procesos de fondo y comprobar corridas completas de las seis cadenas. Ejecutar `python manage.py send_price_alerts` para inspeccionar cuántos envíos están listos sin enviarlos.
7. Activar `SUPERMARKET_EMAILS_ENABLED=true` solamente después del ensayo con email verificado y consentimiento. El comando de envío requiere además `python manage.py send_price_alerts --send`; el scheduler lo invoca con esa opción y respeta la variable.

El código está preparado para el despliegue; ejecutar tareas contra producción y habilitar correos son pasos operativos separados. Para frenar envíos basta desactivar `SUPERMARKET_EMAILS_ENABLED`. Para detener toda recolección, desactivar los procesos de fondo. Las migraciones son aditivas: conservar las tablas permite volver a la imagen anterior sin una migración destructiva.

## Pruebas y operación

`python manage.py test --settings=mysiteFulbo.test_settings` usa SQLite temporal y mocks; no contacta fuentes ni SMTP. `mysiteFulbo.postgres_test_settings` usa PostgreSQL y el backend de correo en memoria; el workflow Application checks lo ejecuta contra un servicio temporal. Las pruebas PostgreSQL cubren búsqueda aproximada e índices.

En administración revisar `SourceRun` (fallos y frescura), `EmailDelivery` (pendientes, reintentos, inciertos), `PriceAlertEvent` y `JobLease`. Revisar filas inciertas manualmente antes de cualquier reenvío. No ejecutar dos versiones diferentes del scheduler durante un cambio de imagen.

## Referencias

Patrones estudiados: [Heisse Preise](https://github.com/badlogic/heissepreise), [PriceBuddy](https://github.com/jez500/pricebuddy), [OpenCesta](https://github.com/ruvelro/opencesta) y [Superprecios Claros](https://github.com/hysmarcos/superprecios-claros). Las fuentes regionales agregadas no se mezclan silenciosamente con precios online de publicaciones concretas.


## Verificación previa al merge — 5 de noviembre de 2026

Se consultaron los árboles de categorías y una muestra de 10 productos de cada una de las seis cadenas. Las seis devolvieron SKUs disponibles con precio y respondieron la consulta puntual por productId utilizada en los seguimientos. La muestra reunió 60 publicaciones con GTIN válido y se procesó en una base temporal, pasando por el guardado real, búsqueda por cadena, filtros, fichas y cotización. Una compra de tres identidades produjo ofertas de las seis cadenas.

La validación conjunta detectó y corrigió una ficha que fallaba cuando el EAN estaba publicado en varias cadenas; la regresión también cubre GTIN con ceros iniciales. Esta comprobación es muestral: la cobertura completa se verifica mediante las corridas de catálogo y sus estados, sin extrapolar estos resultados a todos los productos de cada cadena.
