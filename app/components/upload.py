"""Paso 1: Carga de superficies STL/OBJ/PLY/DXF."""
import streamlit as st
import tempfile
import os
import pathlib

from core import load_mesh, get_mesh_bounds


def render_upload_section() -> bool:
    """Render the file upload UI for design and topo surfaces.

    Returns:
        True if both meshes are loaded in session state.
    """
    st.header("📁 Paso 1: Cargar Superficies STL / DXF")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔵 Superficie de Diseño")
        file_design = st.file_uploader(
            "Cargar Diseño (STL, OBJ, PLY, DXF)",
            type=["stl", "obj", "ply", "dxf"], key="design_file")

    with col2:
        st.subheader("🟢 Superficie Topográfica (As-Built)")
        file_topo = st.file_uploader(
            "Cargar Topografía (STL, OBJ, PLY, DXF)",
            type=["stl", "obj", "ply", "dxf"], key="topo_file")

    if file_design and file_topo:
        ext_d = pathlib.Path(file_design.name).suffix
        ext_t = pathlib.Path(file_topo.name).suffix

        f_design = f_topo = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext_d, delete=False) as f:
                f.write(file_design.read()); f_design = f.name
            with tempfile.NamedTemporaryFile(suffix=ext_t, delete=False) as f:
                f.write(file_topo.read()); f_topo = f.name

            with st.spinner("Cargando superficies..."):
                st.session_state.mesh_design = load_mesh(f_design)
                st.session_state.mesh_topo = load_mesh(f_topo)
                st.session_state.bounds_design = get_mesh_bounds(st.session_state.mesh_design)
                st.session_state.bounds_topo = get_mesh_bounds(st.session_state.mesh_topo)

            col1, col2 = st.columns(2)
            with col1:
                bd = st.session_state.bounds_design
                st.success(f"✅ Diseño cargado: {bd['n_faces']:,} caras, {bd['n_vertices']:,} vértices")
                st.caption(
                    f"X: [{bd['xmin']:.1f}, {bd['xmax']:.1f}] | "
                    f"Y: [{bd['ymin']:.1f}, {bd['ymax']:.1f}] | "
                    f"Z: [{bd['zmin']:.1f}, {bd['zmax']:.1f}]")
            with col2:
                bt = st.session_state.bounds_topo
                st.success(f"✅ Topografía cargada: {bt['n_faces']:,} caras, {bt['n_vertices']:,} vértices")
                st.caption(
                    f"X: [{bt['xmin']:.1f}, {bt['xmax']:.1f}] | "
                    f"Y: [{bt['ymin']:.1f}, {bt['ymax']:.1f}] | "
                    f"Z: [{bt['zmin']:.1f}, {bt['zmax']:.1f}]")

            st.session_state.step = max(st.session_state.step, 2)
        except Exception as e:
            st.error(f"Error al cargar: {e}")
        finally:
            for tmp in (f_design, f_topo):
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)

    return (
        st.session_state.mesh_design is not None
        and st.session_state.mesh_topo is not None
    )
