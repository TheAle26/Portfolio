# Supermarket Tracker

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Personas en Argentina que buscan ahorrar en compras de supermercado desde el celular o la computadora.

## Product Purpose
Buscar productos entre cadenas, armar una compra, comparar su costo real y seguir productos para recibir oportunidades por email.

## Operating Context
Catálogo público sin registro. Una cuenta guarda el carrito y los seguimientos entre dispositivos. No se realizan pagos ni compras dentro del servicio.

## Capabilities and Constraints
Django y PostgreSQL; plantillas con mejoras progresivas. Seis cadenas VTEX: ChangoMás, Carrefour, Disco, Jumbo, Vea y Día. Catálogo diario, revisión de productos seguidos cada seis horas. Los precios corresponden al catálogo online relevado, sin envío ni beneficios bancarios personales. Las promociones por cantidad deben calcularse según las unidades elegidas. Datos de más de 36 horas no participan en recomendaciones actuales.

## Brand Commitments
Nombre público Supermarket Tracker. Ruta /supermarket-tracker/. Mantener enlaces históricos mediante redirecciones. Conservar la identidad reconocible de las etiquetas de precio y reemplazar la navegación centrada en cadenas por búsqueda y planificación.

## Product Principles
- Cantidades y condiciones antes que descuentos llamativos.
- Mostrar cuándo y dónde se verificó un precio.
- Navegar libremente; guardar datos personales solo para su dueño.
- Emails solicitados, con baja sencilla y sin repetir ofertas sin cambios.

## Accessibility & Inclusion
Recorridos por teclado, foco visible, controles etiquetados, contraste AA, movimiento reducido y diseño adaptable. Mantener español e inglés.
