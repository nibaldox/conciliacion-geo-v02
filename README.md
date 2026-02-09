# ⛏️ Conciliación Geotécnica: Diseño vs As-Built

Herramienta para conciliación automática de parámetros geotécnicos de taludes a partir de superficies 3D (STL).

## 📋 Descripción

Carga superficies 3D de diseño y topografía real, genera secciones transversales, extrae automáticamente los parámetros geométricos (altura de banco, ángulo de cara, ancho de berma, ángulos inter-rampa) y evalúa el cumplimiento respecto al diseño.

## 🚀 Instalación

```bash
pip install -r requirements.txt
```

## 💻 Uso

### Interfaz Visual (Streamlit)

```bash
streamlit run app.py
```

Abre el navegador en `http://localhost:8501` y sigue los pasos:

1. **Cargar superficies STL** (diseño y topografía real)
2. **Definir secciones** (manual o automática)
3. **Ejecutar análisis** (corte, extracción, comparación)
4. **Revisar resultados** (perfiles, tabla, dashboard)
5. **Exportar a Excel**

### Línea de Comandos (CLI)

**Con secciones desde archivo JSON:**
```bash
python cli.py \
  --design superficie_diseno.stl \
  --topo superficie_topo.stl \
  --config secciones.json \
  --output resultados.xlsx
```

**Con generación automática de secciones:**
```bash
python cli.py \
  --design superficie_diseno.stl \
  --topo superficie_topo.stl \
  --auto \
  --start "1000,2000" \
  --end "1500,2000" \
  --n 10 \
  --azimuth 0 \
  --length 200 \
  --sector "Sector Norte" \
  --output resultados.xlsx
```

**Con tolerancias personalizadas:**
```bash
python cli.py \
  --design diseno.stl \
  --topo topo.stl \
  --config secciones.json \
  --tol-height "1.0,1.5" \
  --tol-angle "5.0,5.0" \
  --tol-berm "1.0,2.0" \
  --tol-ir "3.0,2.0" \
  --face-threshold 40 \
  --berm-threshold 20
```

## 📐 Formato del Archivo de Secciones (JSON)

```json
{
  "sections": [
    {
      "name": "S-01",
      "sector": "Sector Norte",
      "origin": [1000.0, 2000.0],
      "azimuth": 0.0,
      "length": 200.0
    }
  ]
}
```

- **origin**: coordenadas [X, Y] del punto central de la sección
- **azimuth**: dirección del corte en grados (N=0°, E=90°, S=180°, W=270°)
- **length**: longitud total de la sección en metros

## ⚙️ Parámetros Configurables

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `face-threshold` | 40° | Ángulo mínimo para clasificar segmento como cara de banco |
| `berm-threshold` | 20° | Ángulo máximo para clasificar segmento como berma |
| `resolution` | 0.5 m | Resolución de remuestreo del perfil |
| `tol-height` | -1.0/+1.5 m | Tolerancia de altura de banco |
| `tol-angle` | ±5.0° | Tolerancia de ángulo de cara |
| `tol-berm` | -1.0/+2.0 m | Tolerancia de ancho de berma |
| `tol-ir` | -3.0/+2.0° | Tolerancia de ángulo inter-rampa |

## 📊 Salida Excel

El archivo Excel generado contiene:

- **Resumen**: Información del proyecto y tolerancias
- **Bancos**: Comparación detallada banco por banco
- **Inter-Rampa**: Ángulos inter-rampa y globales
- **Dashboard**: Resumen de cumplimiento con índice global

## 🔧 Tips para Exportar STL desde Vulcan

1. En Vulcan, seleccionar la triangulación (diseño o topografía)
2. `File > Export > Triangulation`
3. Formato: **STL (Binary)**
4. Asegurarse de exportar en las coordenadas originales del proyecto (no trasladar)
5. Exportar diseño y topografía por separado

## 📁 Estructura del Proyecto

```
geoconciliacion/
├── app.py                 # Interfaz Streamlit
├── cli.py                 # Interfaz línea de comandos
├── requirements.txt
├── ejemplo_secciones.json # Ejemplo de configuración
├── test_pipeline.py       # Test con datos sintéticos
└── core/
    ├── __init__.py
    ├── mesh_handler.py    # Carga y manejo de mallas STL
    ├── section_cutter.py  # Generación de secciones transversales
    ├── param_extractor.py # Extracción de parámetros geotécnicos
    └── excel_writer.py    # Exportación a Excel
```
