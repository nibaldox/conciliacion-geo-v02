
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from datetime import datetime
import numpy as np

def create_section_plot(params_design, params_topo, distances_d, elevations_d, distances_t, elevations_t,
                        plot_options=None, section=None, df_pozos=None, filtered_bench_nums=None):
    if plot_options is None:
        plot_options = {}
    show_reconciled = plot_options.get('show_reconciled', True)
    show_areas = plot_options.get('show_areas', False)
    show_semaphore = plot_options.get('show_semaphore', False)
    show_pozos = plot_options.get('show_pozos', False)
    blast_tolerance = plot_options.get('blast_tolerance', 10.0)
    grid_height = plot_options.get('grid_height', 15.0)
    grid_ref = plot_options.get('grid_ref', 0.0)
    tolerances = plot_options.get('tolerances', {})
    if not tolerances:
        tolerances = {'bench_height': {'pos': 1.5}}

    fig, ax = plt.subplots(figsize=(10, 6))

    if len(distances_d) > 0:
        ax.plot(distances_d, elevations_d, color='royalblue', label='Diseño', linewidth=2)

    class ProfileHolder:
        def __init__(self, d, e):
            self.distances = np.array(d)
            self.elevations = np.array(e)

    pd_prof = ProfileHolder(distances_d, elevations_d)
    pt_prof = ProfileHolder(distances_t, elevations_t)

    if show_areas and len(distances_d) > 0 and len(distances_t) > 0:
        from core.geom_utils import calculate_area_between_profiles
        a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)
        mask_u = z_eval_i >= z_ref_i
        if np.any(mask_u):
            ax.fill_between(d_i, z_ref_i, z_eval_i, where=mask_u, facecolor='blue', alpha=0.3)
        mask_o = z_eval_i < z_ref_i
        if np.any(mask_o):
            ax.fill_between(d_i, z_ref_i, z_eval_i, where=mask_o, facecolor='red', alpha=0.3)

    if len(distances_t) > 0:
        if show_semaphore:
            ax.plot(distances_t, elevations_t, color='gray', linewidth=0.5, alpha=0.7)
            from core.geom_utils import calculate_profile_deviation
            devs = calculate_profile_deviation(pd_prof, pt_prof)
            T = tolerances.get('bench_height', {}).get('pos', 1.5)
            
            mask_ok = devs <= T
            mask_warn = (devs > T) & (devs <= 1.5 * T)
            mask_nok = devs > 1.5 * T

            if np.any(mask_ok):
                ax.scatter(distances_t[mask_ok], elevations_t[mask_ok], color='#006100', s=10, zorder=5)
            if np.any(mask_warn):
                ax.scatter(distances_t[mask_warn], elevations_t[mask_warn], color='#FFD700', s=12, zorder=5)
            if np.any(mask_nok):
                ax.scatter(distances_t[mask_nok], elevations_t[mask_nok], color='#FF0000', s=12, zorder=5)
            
            ax.plot([], [], color='forestgreen', linewidth=2, label='Topografía Real')
        else:
            ax.plot(distances_t, elevations_t, color='forestgreen', label='Topografía Real', linewidth=2)

    from core.param_extractor import build_reconciled_profile
    if show_reconciled:
        if params_topo and params_topo.benches:
            rec_dist, rec_elev = build_reconciled_profile(params_topo.benches)
            if len(rec_dist) > 0:
                ax.plot(rec_dist, rec_elev, color='#FF7F0E', label='Conciliado As-Built', linewidth=2.5, zorder=4)
                for b in params_topo.benches:
                    ax.plot(b.crest_distance, b.crest_elevation, marker='d', color='#FF7F0E', markersize=5, zorder=5)
                    ax.plot(b.toe_distance, b.toe_elevation, marker='d', color='#FF7F0E', markersize=5, zorder=5)

            legend_added = False
            for bench in params_topo.benches:
                if bench.spill_width > 0.05 and bench.spill_start_elevation > 0.0:
                    if bench.toe_distance > bench.crest_distance:
                        toe_observed = bench.toe_distance + bench.spill_width
                    else:
                        toe_observed = bench.toe_distance - bench.spill_width

                    d_min = min(bench.spill_start_distance, toe_observed)
                    d_max = max(bench.spill_start_distance, toe_observed)
                    mask = (pt_prof.distances >= d_min - 0.01) & (pt_prof.distances <= d_max + 0.01)
                    topo_x = pt_prof.distances[mask]
                    topo_y = pt_prof.elevations[mask]

                    if len(topo_x) > 0:
                        topo_pts = np.column_stack((topo_x, topo_y))
                        if toe_observed > bench.spill_start_distance:
                            topo_pts = topo_pts[np.argsort(-topo_pts[:, 0])]
                        else:
                            topo_pts = topo_pts[np.argsort(topo_pts[:, 0])]

                        poly_x = [bench.spill_start_distance, bench.toe_distance, toe_observed] + list(topo_pts[:, 0]) + [bench.spill_start_distance]
                        poly_y = [bench.spill_start_elevation, bench.toe_elevation, bench.toe_elevation] + list(topo_pts[:, 1]) + [bench.spill_start_elevation]

                        ax.fill(poly_x, poly_y, color='#FFA500', alpha=0.4, label='Derrame' if not legend_added else None, zorder=3)
                        legend_added = True

        if params_design and params_design.benches:
            rec_d_dist, rec_d_elev = build_reconciled_profile(params_design.benches)
            if len(rec_d_dist) > 0:
                ax.plot(rec_d_dist, rec_d_elev, color='royalblue', linestyle='--', linewidth=1.5, alpha=0.7)

    if params_topo and params_topo.benches:
        for bench in params_topo.benches:
            if filtered_bench_nums is not None and bench.bench_number not in filtered_bench_nums:
                continue
            ax.annotate(f"B{bench.bench_number}", xy=(bench.crest_distance, bench.crest_elevation),
                        xytext=(-8, 8), textcoords='offset points',
                        arrowprops=dict(arrowstyle="->", color="red", alpha=0.6),
                        fontsize=8, color="red")
            ax.annotate(f"Pa{bench.bench_number}", xy=(bench.toe_distance, bench.toe_elevation),
                        xytext=(8, -8), textcoords='offset points',
                        arrowprops=dict(arrowstyle="->", color="darkred", alpha=0.6),
                        fontsize=7, color="darkred")

    if show_pozos and df_pozos is not None and not df_pozos.empty and section is not None:
        from core.calculo_tronadura import proyectar_pozos_en_seccion
        projected = proyectar_pozos_en_seccion(
            df_pozos,
            origin=section.origin,
            azimuth=section.azimuth,
            length=section.length,
            tolerance=blast_tolerance,
        )
        if not projected.empty:
            for _, row in projected.iterrows():
                d_c = row['dist_along']
                d_t = row['dist_along_toe'] if 'dist_along_toe' in row else d_c
                z_c = row['Z_collar']
                z_t = row['Z_toe']
                ax.plot([d_c, d_t], [z_c, z_t], color='orange', linestyle='-', linewidth=1.5, alpha=0.5, zorder=3)
                ax.scatter(d_c, z_c, color='darkorange', s=15, zorder=4)

    all_d = np.concatenate([distances_d, distances_t])
    all_z = np.concatenate([elevations_d, elevations_t])
    valid_d = all_d[np.isfinite(all_d)]
    valid_z = all_z[np.isfinite(all_z)]

    if len(valid_d) > 0 and len(valid_z) > 0:
        xmin, xmax = float(np.min(valid_d)), float(np.max(valid_d))
        x_pad = max((xmax - xmin) * 0.05, 5.0)
        ax.set_xlim(xmin - x_pad, xmax + x_pad)

        if 'z_limits' in plot_options and plot_options['z_limits'] is not None:
            zmin, zmax = plot_options['z_limits']
        else:
            zmin, zmax = float(np.min(valid_z)), float(np.max(valid_z))
            z_pad = max((zmax - zmin) * 0.05, 5.0)
            zmin = zmin - z_pad
            zmax = zmax + z_pad

        ax.set_ylim(zmin, zmax)

        if grid_height is not None and grid_height > 0:
            y_ticks = np.arange(np.floor((zmin - grid_ref) / grid_height) * grid_height + grid_ref,
                                np.ceil((zmax - grid_ref) / grid_height) * grid_height + grid_ref + grid_height,
                                grid_height)
            ax.set_yticks(y_ticks)

    title_name = "N/A"
    title_sector = "N/A"
    if section is not None:
        title_name = section.name
        title_sector = section.sector
    elif params_design is not None:
        title_name = params_design.section_name
        title_sector = params_design.sector
    elif params_topo is not None:
        title_name = params_topo.section_name
        title_sector = params_topo.sector

    ax.set_title(f"Sección: {title_name} - {title_sector}")
    ax.set_xlabel("Distancia (m)")
    ax.set_ylabel("Elevación (m)")
    ax.grid(True, linestyle='--', color='lightgray', alpha=0.7)
    ax.legend(loc='upper right')
    ax.set_aspect('equal', adjustable='box')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def create_compliance_pie_charts(comparisons):
    keys = ['height_status', 'angle_status', 'berm_status']
    labels = ['Altura de Banco', 'Ángulo de Cara', 'Ancho de Berma']
    
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    
    any_data = False
    for idx, (key, title) in enumerate(zip(keys, labels)):
        ax = axes[idx]
        counts = {
            'CUMPLE': sum(1 for c in comparisons if c[key] == "CUMPLE"),
            'FUERA TOL.': sum(1 for c in comparisons if c[key] == "FUERA DE TOLERANCIA"),
            'NO CUMPLE': sum(1 for c in comparisons if c[key] == "NO CUMPLE")
        }
        
        labels_to_show = []
        sizes = []
        colors_to_show = []
        for cat, color in zip(['CUMPLE', 'FUERA TOL.', 'NO CUMPLE'], ['#006100', '#9C5700', '#9C0006']):
            val = counts[cat]
            if val > 0:
                labels_to_show.append(f"{cat}\n({val})")
                sizes.append(val)
                colors_to_show.append(color)
        
        if sum(sizes) > 0:
            any_data = True
            ax.pie(sizes, labels=labels_to_show, autopct='%1.1f%%', startangle=90, colors=colors_to_show,
                   textprops={'fontsize': 9, 'weight': 'bold'})
            ax.set_title(title, fontsize=11, weight='bold', pad=10)
        else:
            ax.text(0.5, 0.5, 'Sin Datos', ha='center', va='center')
            ax.axis('off')
            
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_word_report(comparisons, all_data, output_path, project_info=None,
                         df_pozos=None, sections=None, plot_options=None):
    if project_info is None:
        project_info = {}
        
    doc = Document()
    
    for section in doc.sections:
        section.orientation = WD_ORIENT.LANDSCAPE
        new_width, new_height = section.page_height, section.page_width
        section.page_width = new_width
        section.page_height = new_height
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)

    global_zmin = float('inf')
    global_zmax = float('-inf')
    for item in all_data:
        prof_d = item['profile_d']
        prof_t = item['profile_t']
        if len(prof_d[1]) > 0:
            global_zmin = min(global_zmin, np.min(prof_d[1]))
            global_zmax = max(global_zmax, np.max(prof_d[1]))
        if len(prof_t[1]) > 0:
            global_zmin = min(global_zmin, np.min(prof_t[1]))
            global_zmax = max(global_zmax, np.max(prof_t[1]))

    if global_zmin < float('inf') and global_zmax > float('-inf'):
        z_pad = max((global_zmax - global_zmin) * 0.05, 5.0)
        z_limits = [float(global_zmin - z_pad), float(global_zmax + z_pad)]
    else:
        z_limits = None

    if plot_options is None:
        plot_options = {}
    plot_options['z_limits'] = z_limits
    
    title = doc.add_heading(f"Informe de Conciliación Geotécnica", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    p = doc.add_paragraph()
    p.add_run(f"Proyecto: {project_info.get('project', 'N/A')}\n").bold = True
    p.add_run(f"Elaborado por: {project_info.get('author', 'N/A')}\n")
    p.add_run(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\n")
    
    doc.add_heading("1. Resumen Ejecutivo", level=1)
    
    if comparisons:
        n_total = len(comparisons) * 3
        n_ok = sum(1 for c in comparisons for k in ['height_status','angle_status','berm_status'] if c[k] == "CUMPLE")
        pct = n_ok / n_total * 100 if n_total > 0 else 0
        
        doc.add_paragraph(f"Se evaluaron {len(comparisons)} bancos en total.")
        doc.add_paragraph(f"Cumplimiento Global: {pct:.1f}%")
        
        try:
            pie_stream = create_compliance_pie_charts(comparisons)
            p_pie = doc.add_paragraph()
            p_pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_pie.add_run().add_picture(pie_stream, width=Inches(8.5))
            pie_stream.close()
        except Exception as e:
            doc.add_paragraph(f"(Error al generar gráficos de torta: {e})")

        doc.add_paragraph("Resumen por parámetro:")
        table = doc.add_table(rows=1, cols=4)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Parámetro'
        hdr_cells[1].text = 'CUMPLE'
        hdr_cells[2].text = 'FUERA TOL.'
        hdr_cells[3].text = 'NO CUMPLE'
        
        for col_idx, h in enumerate(['Parámetro', 'CUMPLE', 'FUERA TOL.', 'NO CUMPLE']):
            for paragraph in hdr_cells[col_idx].paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(9.5)

        for key, label in [('height_status', 'Altura'), ('angle_status', 'Ángulo Cara'), ('berm_status', 'Berma')]:
            row_cells = table.add_row().cells
            row_cells[0].text = label
            row_cells[1].text = str(sum(1 for c in comparisons if c[key] == "CUMPLE"))
            row_cells[2].text = str(sum(1 for c in comparisons if c[key] == "FUERA DE TOLERANCIA"))
            row_cells[3].text = str(sum(1 for c in comparisons if c[key] == "NO CUMPLE"))
            for cell in row_cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9.0)
    else:
        doc.add_paragraph("No se encontraron resultados para reportar.")

    doc.add_heading("2. Tabla Resumen de Cumplimiento por Perfil", level=1)
    if comparisons:
        table_summary = doc.add_table(rows=1, cols=5)
        table_summary.style = 'Table Grid'
        
        headers = ['Sección', 'Banco (cota)', 'H. Dise / Real', 'Ang. Dise / Real', 'Berma Dise / Real']
        for col_idx, h in enumerate(headers):
            hdr_cell = table_summary.rows[0].cells[col_idx]
            hdr_cell.text = h
            for paragraph in hdr_cell.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(9.5)
                    
        for c in comparisons:
            row_cells = table_summary.add_row().cells
            row_cells[0].text = c.get('section', 'N/A')
            
            b_num = c.get('bench_num', 'N/A')
            b_level = c.get('level', 'N/A')
            row_cells[1].text = f"B{b_num} ({b_level})"
            
            h_d = f"{c['height_design']:.1f}" if c.get('height_design') is not None else "N/A"
            h_r = f"{c['height_real']:.1f}" if c.get('height_real') is not None else "N/A"
            row_cells[2].text = f"{h_d} / {h_r}"
            
            a_d = f"{c['angle_design']:.1f}" if c.get('angle_design') is not None else "N/A"
            a_r = f"{c['angle_real']:.1f}" if c.get('angle_real') is not None else "N/A"
            row_cells[3].text = f"{a_d} / {a_r}"
            
            b_d = f"{c['berm_design']:.1f}" if c.get('berm_design') is not None else "N/A"
            b_r = f"{c['berm_real']:.1f}" if c.get('berm_real') is not None else "N/A"
            row_cells[4].text = f"{b_d} / {b_r}"
            
            for cell in row_cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8.5)
    else:
        doc.add_paragraph("No hay datos de comparación disponibles.")

    doc.add_page_break()

    doc.add_heading("3. Detalle por Sección", level=1)
    
    valid_items = []
    for item in all_data:
        sec_name = item['section_name']
        sec_comps = [c for c in comparisons if c['section'] == sec_name]
        if sec_comps:
            valid_items.append((item, sec_comps))
            
    for idx, (item, sec_comps) in enumerate(valid_items):
        sec_name = item['section_name']
        doc.add_heading(f"Sección {sec_name}", level=2)
        
        pd = item['params_design']
        pt = item['params_topo']
        prof_d = item['profile_d']
        prof_t = item['profile_t']
        
        sec_obj = None
        if sections:
            for s in sections:
                if s.name == sec_name:
                    sec_obj = s
                    break
                    
        filtered_bench_nums = {c['bench_num'] for c in sec_comps}
        
        img_stream = create_section_plot(
            pd, pt, prof_d[0], prof_d[1], prof_t[0], prof_t[1],
            plot_options=plot_options, section=sec_obj, df_pozos=df_pozos,
            filtered_bench_nums=filtered_bench_nums
        )
        
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.add_run().add_picture(img_stream, width=Inches(6.0))
        img_stream.close()
        
        if (idx + 1) % 3 == 0 and (idx + 1) < len(valid_items):
            doc.add_page_break()
        else:
            doc.add_paragraph()

    if df_pozos is not None and not df_pozos.empty:
        doc.add_page_break()
        doc.add_heading("4. Análisis de Perforación y Tronadura", level=1)

        pasadura = (df_pozos['Z_collar'] - 15.0) - df_pozos['Z_toe']
        p_mean = pasadura.mean()
        p_optimal = ((pasadura >= 0.5) & (pasadura <= 1.5)).sum()
        p_pct = p_optimal / len(df_pozos) * 100 if len(df_pozos) > 0 else 0

        p1 = doc.add_paragraph()
        p1.add_run("Estadísticas Generales de Perforación y Voladura:\n").bold = True
        p1.add_run(f"- Total de Pozos Registrados: {len(df_pozos)}\n")
        p1.add_run(f"- Pasadura Promedio (Sub-drilling): {p_mean:.2f} m\n")
        p1.add_run(f"- Porcentaje de Pozos en Pasadura Óptima (0.5m a 1.5m): {p_pct:.1f}% ({p_optimal} pozos)\n")

        from core.geom_utils import find_df_column
        kg_col = find_df_column(df_pozos, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

        import pandas as pd
        df_comp = pd.DataFrame(comparisons)
        dev_col = None
        for col_name in ['delta_crest', 'height_dev', 'angle_dev']:
            if col_name in df_comp.columns:
                dev_col = col_name
                break

        if sections and kg_col and dev_col:
            doc.add_heading("Cruce de Desviaciones vs Carga de Explosivo", level=2)
            doc.add_paragraph(
                "A continuación se detalla la cantidad de pozos y la carga de explosivo acumulada en un radio de 15 metros "
                "respecto al eje de cada sección transversal, cruzada con su respectiva desviación absoluta media:"
            )

            from core.calculo_tronadura import proyectar_pozos_en_seccion
            table = doc.add_table(rows=1, cols=4)
            table.style = 'Table Grid'

            headers = ["Sección", "Pozos Cercanos", "Kilos de Explosivo", "Desviación Media (m)"]
            for idx, h in enumerate(headers):
                table.rows[0].cells[idx].text = h

            for sec in sections:
                sec_name = sec.name
                df_sec = df_comp[df_comp['section'] == sec_name]
                if df_sec.empty:
                    continue
                avg_dev = df_sec[dev_col].abs().mean()
                proj = proyectar_pozos_en_seccion(
                    df_pozos,
                    origin=sec.origin,
                    azimuth=sec.azimuth,
                    length=sec.length,
                    tolerance=15.0
                )
                if not proj.empty:
                    total_kg = proj[kg_col].fillna(0).sum()
                    num_wells = len(proj)
                else:
                    total_kg = 0
                    num_wells = 0

                row_cells = table.add_row().cells
                row_cells[0].text = sec_name
                row_cells[1].text = str(num_wells)
                row_cells[2].text = f"{total_kg:.0f}"
                row_cells[3].text = f"{avg_dev:.2f}"

    doc.save(output_path)


def generate_section_images_zip(all_data, plot_options=None, sections=None, df_pozos=None, filtered_comps=None):
    import zipfile
    
    global_zmin = float('inf')
    global_zmax = float('-inf')
    for item in all_data:
        prof_d = item['profile_d']
        prof_t = item['profile_t']
        if len(prof_d[1]) > 0:
            global_zmin = min(global_zmin, np.min(prof_d[1]))
            global_zmax = max(global_zmax, np.max(prof_d[1]))
        if len(prof_t[1]) > 0:
            global_zmin = min(global_zmin, np.min(prof_t[1]))
            global_zmax = max(global_zmax, np.max(prof_t[1]))

    if global_zmin < float('inf') and global_zmax > float('-inf'):
        z_pad = max((global_zmax - global_zmin) * 0.05, 5.0)
        z_limits = [float(global_zmin - z_pad), float(global_zmax + z_pad)]
    else:
        z_limits = None

    if plot_options is None:
        plot_options = {}
    plot_options['z_limits'] = z_limits

    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for item in all_data:
            sec_name = item['section_name']
            
            filtered_bench_nums = None
            if filtered_comps:
                sec_comps = [c for c in filtered_comps if c['section'] == sec_name]
                if not sec_comps:
                    continue
                filtered_bench_nums = {c['bench_num'] for c in sec_comps}
            
            pd = item['params_design']
            pt = item['params_topo']
            prof_d = item['profile_d']
            prof_t = item['profile_t']
            
            sec_obj = None
            if sections:
                for s in sections:
                    if s.name == sec_name:
                        sec_obj = s
                        break
            
            img_buf = create_section_plot(
                pd, pt, prof_d[0], prof_d[1], prof_t[0], prof_t[1],
                plot_options=plot_options, section=sec_obj, df_pozos=df_pozos,
                filtered_bench_nums=filtered_bench_nums
            )
            
            filename = f"{sec_name}.png"
            zip_file.writestr(filename, img_buf.getvalue())
            img_buf.close()
            
    zip_buffer.seek(0)
    return zip_buffer
