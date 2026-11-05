---
name: Supermarket Tracker
description: Comparación cotidiana de compras con cantidades y condiciones claras
colors:
  paper: "#f6f3e9"
  surface: "#fffefa"
  ink: "#20211d"
  muted: "#5d6058"
  faint: "#787a71"
  line: "#dcd9ce"
  yellow: "#f1cd42"
  yellow-soft: "#fff2b9"
  green: "#17643e"
  red: "#9a302b"
  focus: "#866400"
typography:
  display:
    fontFamily: "Oswald, Impact, sans-serif"
    fontWeight: 600
    lineHeight: 1.12
  body:
    fontFamily: "Instrument Sans, Arial, sans-serif"
    fontSize: "16px"
    lineHeight: 1.5
    mobileFontSize: "15px"
spacing:
  compact: "8px"
  control: "12px"
  group: "24px"
  section: "44px"
components:
  button-primary:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.ink}"
---

## Overview

La identidad de etiqueta de precio se conserva como lenguaje de lectura, sin decoración de tickets o códigos de barras. La tarea gobierna: buscar, elegir cantidades, cotizar y seguir. Modo de la superficie: Operate.

## Colors

Papel cálido para lectura diurna, grafito para navegación y texto, amarillo para acciones y oportunidades. Verde indica ahorro verificable; rojo comunica errores. Los nombres de las cadenas identifican el origen de cada precio; el CSS del tracker no les asigna colores propios.

## Typography

Instrument Sans para nombres, instrucciones y controles; el texto base pasa de 16 px a 15 px en pantallas de hasta 600 px. Oswald (con Impact como respaldo) se usa para títulos y precios destacados. Los importes usan números tabulares y formato local. Los nombres largos deben poder leerse; los códigos técnicos quedan en segundo plano.

## Layout

Cabecera global, búsqueda principal y filtros agrupados en details. A 850 px o menos la navegación pasa a su propia fila, la búsqueda se apila y el catálogo usa una columna; a 600 px o menos la grilla de productos usa dos columnas y se reducen padding e imágenes. El carrito se lee como tabla en escritorio y como filas de producto con nombres de tienda visibles en celular. Ninguna tabla debe ensanchar la página.

## Elevation & Depth

Superficies y bordes organizan la información. Las sombras son suaves y secundarias. No se anidan paneles decorativos.

## Components

Los enlaces abren fichas; los botones de cantidad son controles independientes. Toda ficha ofrece carrito y seguimiento. El carrito muestra cobertura y subtotales incompletos sin adjudicarles el mejor precio. La carga, los conflictos de sincronización y los errores de red tienen texto visible y recuperación.

## Do's and Don'ts

- Mostrar precio por unidad, cantidad y condiciones de promoción por separado.
- Mostrar fecha de observación y mantener accesible el historial.
- Usar foco visible, etiquetas de formulario y anuncios aria-live para cambios.
- Mantener las acciones táctiles amplias y respetar movimiento reducido.
- No confundir ahorro histórico con descuento sobre precio de lista.
- No mostrar una compra incompleta como ganadora.
