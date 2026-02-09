#!/usr/bin/env python3
"""
CLI para Conciliación Geotécnica: Diseño vs As-Built
Uso:
  python cli.py --design superficie_diseno.stl --topo superficie_topo.stl --config secciones.json
  python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0
"""
import argparse
import json
import sys
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from core import (
    load_mesh, get_mesh_bounds,
    SectionLine, cut_mesh_with_section,
    extract_parameters, compare_design_vs_asbuilt, export_results,
    generate_word_report,
)
from core.section_cutter import generate_sections_along_crest


def parse_args():
    parser = argparse.ArgumentParser(description="Conciliación Geotécnica: Diseño vs As-Built")
    parser.add_argument("--design", required=True, help="Archivo STL/OBJ/DXF superficie de diseño")
    parser.add_argument("--topo", required=True, help="Archivo STL/OBJ/DXF superficie topográfica real")
    parser.add_argument("--output", default="Conciliacion_Resultados.xlsx", help="Archivo Excel de salida")
    parser.add_argument("--report", help="Archivo Word de reporte (opcional, ej: Reporte.docx)")
    
    # Secciones desde archivo JSON
    parser.add_argument("--config", help="Archivo JSON con definición de secciones")
    
    # Generación automática de secciones
    parser.add_argument("--auto", action="store_true", help="Generar secciones automáticamente")
    parser.add_argument("--start", help="Punto inicio 'X,Y' para generación automática")
    parser.add_argument("--end", help="Punto fin 'X,Y' para generación automática")
    parser.add_argument("--n", type=int, default=5, help="Número de secciones")
    parser.add_argument("--azimuth", type=float, default=None, help="Azimut de corte (°). Si no se indica, es perpendicular a la línea.")
    parser.add_argument("--auto-azimuth", action="store_true", help="[NO RECOMENDADO] Usar pendiente local del diseño (ruidoso)")
    parser.add_argument("--length", type=float, default=200.0, help="Longitud de secciones (m)")
    parser.add_argument("--sector", default="General", help="Nombre del sector")
    
    # Tolerancias
    parser.add_argument("--tol-height", default="1.0,1.5", help="Tolerancia altura '-,+' en m")
    parser.add_argument("--tol-angle", default="5.0,5.0", help="Tolerancia ángulo cara '-,+' en °")
    parser.add_argument("--min-berm", type=float, default=6.0, help="Berma mínima (m)")
    parser.add_argument("--tol-ir", default="3.0,2.0", help="Tolerancia inter-rampa '-,+' en °")
    
    # Detección
    parser.add_argument("--face-threshold", type=float, default=40.0, help="Ángulo mínimo cara (°)")
    parser.add_argument("--berm-threshold", type=float, default=20.0, help="Ángulo máximo berma (°)")
    parser.add_argument("--resolution", type=float, default=0.5, help="Resolución de perfil (m)")
    
    # Info proyecto
    parser.add_argument("--project", default="", help="Nombre del proyecto")
    parser.add_argument("--author", default="", help="Elaborado por")
    
    return parser.parse_args()


def parse_tolerance(tol_str):
    parts = tol_str.split(",")
    return {'neg': float(parts[0]), 'pos': float(parts[1])}


def load_sections_from_json(filepath):
    """Carga secciones desde archivo JSON."""
    with open(filepath) as f:
        data = json.load(f)
    
    sections = []
    for s in data.get("sections", []):
        sections.append(SectionLine(
            name=s["name"],
            origin=np.array(s["origin"]),
            azimuth=s["azimuth"],
            length=s.get("length", 200.0),
            sector=s.get("sector", ""),
        ))
    return sections


def main():
    args = parse_args()
    
    # Parsear tolerancias
    tolerances = {
        'bench_height': parse_tolerance(args.tol_height),
        'face_angle': parse_tolerance(args.tol_angle),
        'berm_width': {'min': args.min_berm},
        'inter_ramp_angle': parse_tolerance(args.tol_ir),
        'overall_angle': {'neg': 2.0, 'pos': 2.0},
    }
    
    # Cargar superficies
    print(f"📂 Cargando superficie de diseño: {args.design}")
    mesh_design = load_mesh(args.design)
    bounds_d = get_mesh_bounds(mesh_design)
    print(f"   ✅ {bounds_d['n_faces']:,} caras | Z: [{bounds_d['zmin']:.1f}, {bounds_d['zmax']:.1f}]")
    
    print(f"📂 Cargando superficie topográfica: {args.topo}")
    mesh_topo = load_mesh(args.topo)
    bounds_t = get_mesh_bounds(mesh_topo)
    print(f"   ✅ {bounds_t['n_faces']:,} caras | Z: [{bounds_t['zmin']:.1f}, {bounds_t['zmax']:.1f}]")
    
    # Definir secciones
    if args.config:
        print(f"📋 Cargando secciones desde: {args.config}")
        sections = load_sections_from_json(args.config)
    elif args.auto:
        if not args.start or not args.end:
            print("❌ Se requiere --start y --end para generación automática")
            sys.exit(1)
        start = np.array([float(x) for x in args.start.split(",")])
        end = np.array([float(x) for x in args.end.split(",")])
        print(f"🔄 Generando {args.n} secciones automáticas...")
        
        # If azimuth is None, it will be calculated perpendicular to the line
        sec_az = args.azimuth
            
        sections = generate_sections_along_crest(
            mesh_design, start, end, args.n,
            sec_az, args.length, args.sector
        )

        if args.auto_azimuth:
            from core.section_cutter import compute_local_azimuth
            print("⚠️ ADVERTENCIA: Usando cálculo de azimut por pendiente local (puede ser ruidoso)")
            for sec in sections:
                # CRITICAL: Always use design mesh for azimuth
                sec.azimuth = compute_local_azimuth(mesh_design, sec.origin)
    else:
        print("❌ Debe especificar --config o --auto para definir secciones")
        sys.exit(1)
    
    print(f"✂️  {len(sections)} secciones definidas")
    
    # Procesar secciones
    params_design = []
    params_topo = []
    comparisons = []
    
    # Store data for report
    report_data = []

    for i, section in enumerate(sections):
        print(f"   Procesando {section.name}...", end=" ")
        
        pd = cut_mesh_with_section(mesh_design, section)
        pt = cut_mesh_with_section(mesh_topo, section)
        
        if pd is None or pt is None:
            print("⚠️ Sin intersección")
            continue
        
        ep_d = extract_parameters(pd.distances, pd.elevations,
            section.name, section.sector, args.resolution,
            args.face_threshold, args.berm_threshold)
        ep_t = extract_parameters(pt.distances, pt.elevations,
            section.name, section.sector, args.resolution,
            args.face_threshold, args.berm_threshold)
        
        params_design.append(ep_d)
        params_topo.append(ep_t)
        
        # Save profile data for report
        if args.report:
            report_data.append({
                'section_name': section.name,
                'params_design': ep_d,
                'params_topo': ep_t,
                'profile_d': (pd.distances, pd.elevations),
                'profile_t': (pt.distances, pt.elevations),
            })
        
        if ep_d.benches and ep_t.benches:
            comp = compare_design_vs_asbuilt(ep_d, ep_t, tolerances)
            comparisons.extend(comp)
            print(f"✅ {len(ep_d.benches)} bancos diseño, {len(ep_t.benches)} bancos real")
        else:
            print(f"⚠️ Bancos: diseño={len(ep_d.benches)}, real={len(ep_t.benches)}")
    
    # Resumen
    if comparisons:
        n_total = len(comparisons) * 3
        n_ok = sum(1 for c in comparisons for k in ['height_status','angle_status','berm_status'] if c[k] == "CUMPLE")
        pct = n_ok / n_total * 100
        
        print(f"\n📊 RESUMEN DE CUMPLIMIENTO")
        print(f"   Bancos evaluados: {len(comparisons)}")
        print(f"   Evaluaciones totales: {n_total}")
        print(f"   Cumplimiento global: {pct:.1f}%")
        
        # Exportar
        project_info = {
            'project': args.project, 'author': args.author,
            'date': datetime.now().strftime("%d/%m/%Y"),
        }
        export_results(comparisons, params_design, params_topo,
            tolerances, args.output, project_info)
        print(f"\n💾 Resultados Excel exportados a: {args.output}")
        
        if args.report and report_data:
            print(f"📄 Generando reporte Word en: {args.report}")
            try:
                generate_word_report(comparisons, report_data, args.report, project_info)
                print(f"✅ Reporte generado exitosamente.")
            except Exception as e:
                print(f"❌ Error generando reporte: {e}")
        elif args.report:
            print("⚠️ No hay datos suficientes para el reporte.")

        print("   Verifica que las secciones intersecten ambas superficies.")


if __name__ == "__main__":
    main()
