Alejo Vincent | Portfolio & Home Server Hub


## Sobre el Proyecto

Este repositorio contiene el código fuente de mi portafolio personal interactivo. Más que una simple *landing page* estática, este proyecto funciona como el nodo central (Hub) de mi ecosistema de aplicaciones.

Está desarrollado íntegramente en *Django* y se encuentra alojado y servido al mundo desde un servidor local (una Raspberry Pi) configurado desde cero en mi propia casa. Demuestra no solo mis capacidades en el desarrollo Backend, sino también habilidades sólidas en infraestructura, redes, despliegue de microservicios y filosofía DevOps.

---

## Arquitectura y Tecnologías

El sistema está diseñado para ser resiliente, seguro y completamente autocontenido. La pila tecnológica utilizada para su arquitectura incluye:

* **Backend:** Python + Django
* **Frontend:** HTML5, CSS puro, Bootstrap 5 y FontAwesome. Sistema de *templates* integrados para la descarga dinámica de estáticos (CV).
* **Base de Datos:** PostgreSQL (gestiona la persistencia de datos de todo el ecosistema).
* **Contenedores:** Docker & Docker Compose para orquestar la aplicación de forma segura, aislando procesos y evitando la ejecución con privilegios root en los contenedores de la aplicación.
* **Servidor Web / Proxy Inverso:** Nginx (gestiona los certificados HTTPS, enruta el tráfico interno y sirve los archivos estáticos).
* **Servidor de Aplicaciones:** Gunicorn.
* **Infraestructura:** Raspberry Pi corriendo Linux (Debian-based), con gestión de seguridad por SSH.
* **Red:** Dynamic DNS (No-IP) para el enrutamiento del dominio hacia una IP dinámica.

---

## 🌐 El Ecosistema (Proyectos Integrados)

Desde este portafolio se documenta y se brinda acceso a las aplicaciones reales que componen mi entorno de desarrollo. Todo el código convive y es orquestado por este mismo repositorio:

### 1. 🛰️ IoT Tracking Dashboard
Sistema de telemetría en tiempo real para flotas logísticas.
* **Integración Hardware:** Utilisasion de dispositivos físicos Teltonika (FMC150) vía la plataforma Flespi. 
* **Simulación de Rutas:** Motor de simulación en vivo procesando archivos `.gpx` y calculando variables físicas reales (Fórmula de Haversine para distancias, consumo de combustible, voltaje).
* **Reportes Automatizados:** Tareas programadas en segundo plano con `APScheduler` bajo el patrón *Catch-Up* para garantizar la generación de reportes diarios ante caídas del servidor o cortes de luz.(En un futuro)

### 2. 💊 FarmaGo
Plataforma de delivery con control estricto de accesos.
* **Arquitectura de Roles:** Gestión de tres entidades independientes (Cliente, Farmacia, Repartidor).
* **Seguridad:** Implementación de un modelo de usuario personalizado (`Custom User Model`) y validaciones de datos estrictas mediante Regex.

### 3. ⚽ FulboApp
Sistema integral de gestión deportiva amateur.
* Desarrollado en Django, enfocado en el modelado de datos relacionales robustos y la experiencia de usuario a través de paneles de administración protegidos.

### 4. 🛒 Tracker de precios de supermercados
Seguimiento diario de catálogo, disponibilidad, promociones e historial de 30 días para **ChangoMás, Carrefour y Disco**, consumiendo sus catálogos públicos de VTEX.
* **API REST:** endpoints de solo lectura en `/api/v1/supermarkets/stores/` y `/api/v1/supermarkets/products/`.
* **Preparado para comparación:** cada publicación queda aislada por supermercado y conserva el EAN como identificador compartido.
* **Actualización:** `python manage.py scrape_supermarkets` releva las tres cadenas; `--store carrefour` permite ejecutar una sola.

---

## 📬 Contacto

¿Interesado en mi perfil para una primera experiencia formal en el sector IT como Trainee/Junior? ¡Hablemos!

* **Email:** alejo.vincent26@gmail.com
* **LinkedIn:** [Alejo Vincent](https://www.linkedin.com/in/alejo-vincent-37aa63220/)
* **GitHub:** [@TheAle26](https://github.com/TheAle26)
