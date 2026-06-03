
# ⛏️ Conciliación Geotécnica: Diseño vs As-Built

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
![React](https://img.shields.io/badge/React-19-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6)
![License](https://img.shields.io/badge/License-MIT-green)

Herramienta avanzada para la conciliación geotécnica en minería a cielo abierto. Permite comparar superficies de diseño (fases) con levantamientos topográficos reales (As-Built) mediante el análisis automático de perfiles transversales.

## 📸 Capturas de Pantalla

| Carga de Datos y Configuración | Análisis de Perfiles |
|:------------------------------:|:--------------------:|
| ![Dashboard Overview](printscr/dashboard-overview.png) | ![Profile Analysis](printscr/profile-analysis.png) |
| *Interfaz principal para carga de mallas y configuración de tolerancias* | *Visualización interactiva de perfiles con detección de bancos y bermas* |

| Definición de Secciones | Reportes Detallados |
|:-----------------------:|:-------------------:|
| ![Section Definition](printscr/section-definition.png) | ![Parameter Settings](printscr/parameter-settings.png) |
| *Generación automática y manual de secciones de corte* | *Configuración de parámetros de detección (RDP, ángulos)* |

---

## 🏗️ Web App v2

La versión 2 introduce una arquitectura moderna **React + FastAPI** que reemplaza la interfaz Streamlit legacy con una aplicación web de alto rendimiento.

### Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│  React 19 + TypeScript  (Vite)                          │
│  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ │
│  │  CesiumJS  │ │ Plotly.js│ │TanStack   │ │ Zustand  │ │
│  │  3D View   │ │ Profiles │ │Table+Query│ │  State   │ │
│  └─────┬──────┘ └────┬─────┘ └─────┬─────┘ └────┬─────┘ │
│        └──────────────┴────────────┴─────────────┘       │
│                          │  HTTP / REST                   │
├──────────────────────────┼────────────────────────────────┤
│  FastAPI  (Python)       │                                │
│  ┌───────────┐ ┌────────┴──────┐ ┌──────────────────┐    │
│  │  Routers   │ │ Core Library  │ │   SQLite DB      │    │
│  │  /sessions │ │ mesh_handler  │ │   (sessions)     │    │
│  │  /meshes   │ │ section_cutter│ │                  │    │
│  │  /sections │ │ param_extract │ └──────────────────┘    │
│  │  /export   │ │ excel_writer  │                         │
│  └───────────┘ │ report_gen    │                         │
│                └───────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 19 | UI framework |
| Frontend | TypeScript | Type safety |
| Frontend | Vite 6 | Build tool & dev server |
| Frontend | Tailwind CSS v4 | Utility-first styling |
| Frontend | CesiumJS | 3D terrain visualization |
| Frontend | Plotly.js | Interactive profile charts |
| Frontend | TanStack Table | Data grid with sorting/filtering |
| Frontend | TanStack Query | Server state management |
| Frontend | Zustand | Client state management |
| Backend | FastAPI | REST API framework |
| Backend | SQLite | Session persistence |
| Backend | trimesh | 3D mesh processing |
| Backend | OpenAI / LM Studio | AI report generation |

---

## 🚀 Quick Start

### Docker (Production)

```bash
docker compose up --build
```

Frontend at `http://localhost:5173`, API at `http://localhost:8000`.

### Development (Local)

```bash
# 1. Backend
pip install -e .
uvicorn api.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd web && npm install && npm run dev
```

Or use the convenience script:

```bash
./dev.sh
```

### API Documentation

Swagger UI available at `http://localhost:8000/docs` when the backend is running.

---

## 🚀 Características Principales

Esta aplicación automatiza el flujo de trabajo de conciliación geotécnica, reduciendo el tiempo de análisis de horas a minutos.

### 1. Carga y Procesamiento de Mallas 3D
*   Soporte para formatos **STL, OBJ, PLY, DXF**.
*   Visualización interactiva de nubes de puntos y mallas trianguladas.
*   Alineación automática de sistemas de coordenadas.

### 2. Definición Flexible y Acumulativa de Secciones
*   **Carga Multi-Archivo Acumulativa**: Soporte para la carga sucesiva de múltiples archivos DXF/CSV en memoria de forma acumulada y concurrente.
*   **Sufijos de Sector Automáticos**: Los perfiles adoptan sufijos basados en el nombre de archivo origen (ej. `S01-f9`, `S02-f10`), facilitando la comparación paralela de múltiples sectores y fases de la mina sin colisiones.
*   **Trazabilidad Espacial**: Columna `"Archivo"` integrada en la tabla de secciones del Paso 2 para conocer de manera unívoca la procedencia de cada línea de corte.
*   **Métodos de Entrada**: Archivos de coordenadas, interactivo por clic en plano 3D, coordenadas manuales y equiespaciadas automáticas a lo largo de una línea de cresta.
*   **Herramienta de Reinicio**: Botón `"Limpiar Secciones"` para vaciar el pool acumulativo e iniciar nuevas evaluaciones limpias al instante.

### 3. Extracción Automática de Parámetros
El algoritmo inteligente identifica y calcula:
*   **Altura de Banco**: Distancia vertical entre pata y cresta.
*   **Ancho de Berma Total y Desglose**:
    *   **Ancho de Berma Total**: Distancia horizontal total calculada entre pata superior y cresta inferior.
    *   **Berma de Derrame (Material Acumulado)**: Identificación del ancho ocupado por material suelto acumulado al pie del banco (`spill_width`), a partir de la estimación del punto de quiebre (knickpoint) por segunda derivada.
    *   **Berma Efectiva**: Ancho de berma real útil y transitable (`effective_berm_width`), correspondiente a la berma total menos el derrame del banco superior.
*   **Ángulo de Cara y Proyección Sólida**:
    *   **Ángulo de Cara**: Inclinación de la cara de roca sana o competente.
    *   **Pata Sólida Proyectada**: Reconstrucción de la línea de talud de roca competente mediante regresión lineal y proyección matemática hasta el nivel del piso, deduciendo la posición teórica original de la pata antes del derrame.
*   **Ángulo Inter-rampa**: Pendiente global entre bancos.
*   **Detección de Rampas**: Identificación automática de rampas basada en anchos de berma (15m - 42m).

### 4. Conciliación Diseño vs Real
*   **Matching Inteligente**: Algoritmo húngaro para emparejar bancos de diseño con los reales basado en elevación.
*   **Semáforos de Cumplimiento**: Visualización rápida de desviaciones (Verde/Amarillo/Rojo) según tolerancias configurables.
*   **Cálculo de Volúmenes**: Estimación de áreas de corte (sobre-excavación) y relleno (bancos colgados) por sección.

### 5. Ergonomía Visual en Perfiles Cross-Section
*   **Grilla Multicolumna Dinámica**: Selector en pantalla para visualizar perfiles en 1, 2 o 3 columnas de forma adaptativa, minimizando el scrolling vertical.
*   **Cabecera de Mandos Compacta**: Mandos de control (área, semáforo, derrame, pozos, perfiles) reestructurados horizontalmente en una cabecera de 5 columnas para aprovechar al máximo el espacio de la aplicación.
*   **Visualización Dinámica del Área de Derrame**: Representación visual premium de las pilas de derrame acumuladas al pie del talud como polígonos cerrados sombreados en color naranja semi-transparente (`rgba(255, 165, 0, 0.4)`), delimitados por la cara proyectada de roca sana, el piso horizontal y la topografía real.
*   **Encuadre Bounding Box y Relación 1:1**: Centrado simétrico inteligente con un 5% de margen (padding) focalizado en el talud, forzando una escala geométrica estricta de 1:1 en pantalla.
*   **Leyendas Simplificadas**: Caja de leyendas despejada de contaminación visual, ocultando trazas auxiliares (Deuda, Sobre-excavación, Info Bancos, Semáforos, Pozos) para reflejar únicamente las series clave: `Diseño`, `Topografía Real`, `Conciliado As-Built` y `Derrame`.

### 6. Reportabilidad y Exportación de Alta Fidelidad
*   **Tablas Interactivas**: Filtrado por Sector, Nivel y Sección. Ordenamiento flexible con coloreado de cumplimiento.
*   **Exportación a Excel**: Reporte de parámetros y perforaciones compatible con software minero.
*   **Generador de Informes Word (.docx) Dinámico**:
    *   **Filtrado Integrado en Reportes**: El informe de Word y el ZIP de imágenes leen los filtros activos de la tabla (Sector, Nivel, Sección, Banco) en tiempo real.
    *   **Exclusión de Secciones Vacías**: Omite secciones de la mina que no coincidan con la selección activa, generando un reporte Word enfocado únicamente en la zona buscada.
    *   **Coherencia de Grilla e Imágenes**: Los gráficos exportados en Word y ZIP se alinean exactamente con la cota de referencia (`grid_ref`) y la altura de banco (`grid_height`) configuradas, preservando la escala y vistas seleccionadas.
    *   **Anotaciones Focalizadas**: Muestra rótulos de bancos (`B1`, `Pa1`) de Matplotlib únicamente sobre las cotas filtradas.

### 7. Asistente IA para Reportes 🤖
*   **Generación Automática**: Redacción de informes ejecutivos en lenguaje natural.
*   **Soporte Multi-Modelo**:
    *   **Cloud**: OpenAI (GPT-3.5, GPT-4).
    *   **Local**: Integración con LM Studio / Ollama para privacidad total de datos.
*   **Análisis Inteligente**: Identificación de tendencias y recomendaciones operativas.

---

## 🛠️ Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone https://github.com/nibaldox/conciliacion-geo-v02.git
    cd conciliacion-geo-v02
    ```

2.  **Crear un entorno virtual (recomendado):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    # o bien, instalar el paquete en modo desarrollo:
    pip install -e .
    ```

4.  **Frontend (Web App v2):**
    ```bash
    cd web
    npm install
    ```

## ▶️ Uso

### Web App v2 (React + FastAPI)

```bash
# Start both servers
./dev.sh

# Or manually:
uvicorn api.main:app --reload --port 8000   # Backend
cd web && npm run dev                        # Frontend
```

### Streamlit (v1 + módulo Tronadura)

```bash
streamlit run app.py
```

`app.py` actúa como **router con dos módulos accesibles desde la barra lateral**:

- **⛏️ Conciliación Geotécnica** — flujo de 4 pasos (carga → secciones → análisis → resultados)
- **💥 Análisis de Tronadura** — Drill & Blast: sube un reporte de pozos (CSV/XLSX) y visualiza trayectorias 3D, correlación con las secciones geotécnicas y métricas de pasadura

Columnas esperadas en el reporte de pozos (formato ENAEX): `Latitud_Geo`, `Longitud_Geo`, `Nombre_Banco`, `Inclinacion_real`, `Azimuth_real`, `longitud_real`, `Kilos_Cargados_real` (opcional), `fecha_tronadura` (opcional).

### Línea de Comandos (CLI)

```bash
# Generación automática de secciones
python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200

# Con archivo JSON de secciones
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json

# Con tolerancias personalizadas y reporte Word
python cli.py --design diseno.stl --topo topo.stl --config secciones.json \
  --tol-height "1.0,1.5" --tol-angle "5.0,5.0" --report Reporte.docx
```

### Flujo de Trabajo Típico (UI)
1.  **Cargar Superficies**: Sube tus archivos `.stl` de Diseño y Topografía.
2.  **Definir Secciones**: Sube un archivo CSV/DXF con las líneas de corte, o dibújalas interactivamente.
3.  **Procesar**: Haz clic en "Ejecutar Análisis".
4.  **Analizar**: Revisa los perfiles interactivos y la tabla de resultados. Aplica filtros para focalizarte en áreas críticas.
5.  **Exportar**: Descarga el reporte Excel para compartir los hallazgos.

---

## ⚙️ Configuración

### Parámetros de Detección (ajustables en la UI)

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `face_threshold` | 40° | Ángulo mínimo para clasificar un segmento como "Cara" |
| `berm_threshold` | 20° | Ángulo máximo para clasificar un segmento como "Berma" |
| `simplify_epsilon` | — | Tolerancia RDP para suavizar perfiles ruidosos |

### Tolerancias de Cumplimiento (configurables por parámetro)

| Parámetro | Tolerancia Default |
|-----------|-------------------|
| Altura de banco | ±1.0 / +1.5 m |
| Ángulo de cara | ±5.0° |
| Ancho de berma | mín. 6.0 m |
| Ángulo inter-rampa | −3.0° / +2.0° |

**Estado triad**: CUMPLE / FUERA DE TOLERANCIA (hasta 1.5× tolerancia) / NO CUMPLE (>1.5× tolerancia).

---

## 🧪 Desarrollo

```bash
pytest tests/ -v                    # Suite de tests unitarios
python test_pipeline.py             # Test de integración con datos sintéticos
uvicorn api.main:app --reload       # API de desarrollo (:8000)
cd web && npm run dev               # Frontend de desarrollo (:5173)
```

### Convenciones

- **Código**: Inglés (variables, funciones, docstrings)
- **UI/labels**: Español
- **Unidades**: metros (m), grados (°), porcentaje (%)
- **Coordenadas**: Este (X), Norte (Y), Elevación (Z) — sistema minero estándar
- **Azimut**: Grados desde Norte, sentido horario (N=0°, E=90°, S=180°, W=270°)

---

## 🤖 Configuración IA (Agente de Reportes)
Para habilitar la generación de informes con Inteligencia Artificial:
1.  Activa el checkbox **"Habilitar Asistente IA"** en la barra lateral.
2.  Selecciona el Proveedor:
    *   **OpenAI**: Ingresa tu API Key (no se guarda, solo se usa en sesión).
    *   **Local**: Asegúrate de tener **LM Studio** u **Ollama** corriendo (ej. `http://localhost:1234/v1`).
3.  Ve a la pestaña **"🤖 Informe IA"** en Resultados y genera tu reporte.

## 🤝 Contribución

¡Las contribuciones son bienvenidas! Por favor, abre un issue para discutir cambios mayores o envía un Pull Request directo.

## 📄 Licencia

Este proyecto es de uso privado. Todos los derechos reservados.

---
*Desarrollado con ❤️ para la minería moderna.*
