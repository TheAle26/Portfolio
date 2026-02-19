# --- ETAPA 1: Construcción (Builder) ---
FROM python:3.13-slim AS builder

# Crear directorio y variables
RUN mkdir /app
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1 

# Instalar dependencias del sistema para compilar drivers de base de datos
RUN apt-get update \
    && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
RUN pip install --upgrade pip 
COPY requirements.txt /app/ 
RUN pip install --no-cache-dir -r requirements.txt

# --- ETAPA 2: Producción ---
FROM python:3.13-slim

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1 

# Instalar librería de ejecución para la base de datos (sin compiladores)
RUN apt-get update \
    && apt-get install -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario, directorio y asignar permisos
RUN useradd -m -r appuser && \
    mkdir /app && \
    chown -R appuser /app

# Copiar dependencias desde el builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

WORKDIR /app

# Copiar código fuente con dueño correcto
COPY --chown=appuser:appuser . .

# Dar permisos de ejecución MIENTRAS SOMOS ROOT
RUN chmod +x /app/entrypoint.prod.sh

# AHORA SÍ, cambiamos al usuario sin privilegios
USER appuser

EXPOSE 8000 

CMD ["/app/entrypoint.prod.sh"]