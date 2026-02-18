import { useState, useCallback, useMemo, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { updateReconciled } from '../api';

/**
 * Interactive Profile Chart with draggable crest/toe points.
 * 
 * Props:
 *   profileData    - object from /api/profiles/:idx
 *   sectionIndex   - index of current section
 *   onBenchUpdate  - callback when benches are updated
 */
export default function ProfileChart({ profileData, sectionIndex, onBenchUpdate }) {
    const [draggedBenches, setDraggedBenches] = useState(null);
    const [saving, setSaving] = useState(false);

    // Reset local edits when section changes
    useEffect(() => {
        setDraggedBenches(null);
    }, [sectionIndex]);

    const benches = draggedBenches || profileData?.benches_topo || [];

    // Build Plotly traces
    const traces = useMemo(() => {
        if (!profileData) return [];

        const t = [];

        // 1. Design profile
        if (profileData.design) {
            t.push({
                x: profileData.design.distances,
                y: profileData.design.elevations,
                mode: 'lines',
                name: 'Diseño',
                line: { color: '#06b6d4', width: 1.5 },
                hoverinfo: 'x+y',
            });
        }

        // 2. Topo (as-built) profile
        if (profileData.topo) {
            t.push({
                x: profileData.topo.distances,
                y: profileData.topo.elevations,
                mode: 'lines',
                name: 'Topografía Real',
                line: { color: '#10b981', width: 2 },
                hoverinfo: 'x+y',
            });
        }

        // 3. Reconciled Design
        if (profileData.reconciled_design?.distances?.length > 0) {
            t.push({
                x: profileData.reconciled_design.distances,
                y: profileData.reconciled_design.elevations,
                mode: 'lines',
                name: 'Conciliado Diseño',
                line: { color: '#3b82f6', width: 1.5, dash: 'dash' },
                hoverinfo: 'x+y',
            });
        }

        // 4. Reconciled Topo (from benches — this is the editable one)
        if (benches.length > 0) {
            const recDist = [];
            const recElev = [];
            // Build reconciled polyline: Crest1 → Toe1 → Crest2 → Toe2 ...
            const sorted = [...benches].sort((a, b) => a.crest_distance - b.crest_distance);
            for (const b of sorted) {
                recDist.push(b.crest_distance, b.toe_distance);
                recElev.push(b.crest_elevation, b.toe_elevation);
            }
            t.push({
                x: recDist,
                y: recElev,
                mode: 'lines',
                name: 'Conciliado As-Built',
                line: { color: '#f59e0b', width: 2.5 },
                hoverinfo: 'x+y',
            });
        }

        // 5. Draggable Crest points (separate trace for click detection)
        if (benches.length > 0) {
            t.push({
                x: benches.map(b => b.crest_distance),
                y: benches.map(b => b.crest_elevation),
                mode: 'markers',
                name: 'Cresta',
                marker: {
                    color: '#ef4444',
                    size: 12,
                    symbol: 'triangle-up',
                    line: { width: 2, color: '#fff' },
                },
                text: benches.map(b => `B${b.bench_number} Cresta\nDist: ${b.crest_distance.toFixed(1)}m\nElev: ${b.crest_elevation.toFixed(1)}m`),
                hoverinfo: 'text',
                customdata: benches.map((b, i) => ({ type: 'crest', idx: i })),
            });

            // 6. Draggable Toe points
            t.push({
                x: benches.map(b => b.toe_distance),
                y: benches.map(b => b.toe_elevation),
                mode: 'markers',
                name: 'Pie',
                marker: {
                    color: '#8b5cf6',
                    size: 12,
                    symbol: 'triangle-down',
                    line: { width: 2, color: '#fff' },
                },
                text: benches.map(b => `B${b.bench_number} Pie\nDist: ${b.toe_distance.toFixed(1)}m\nElev: ${b.toe_elevation.toFixed(1)}m`),
                hoverinfo: 'text',
                customdata: benches.map((b, i) => ({ type: 'toe', idx: i })),
            });
        }

        return t;
    }, [profileData, benches]);

    const layout = useMemo(() => ({
        title: {
            text: profileData
                ? `Sección ${profileData.section_name} — ${profileData.sector}`
                : 'Selecciona una sección',
            font: { color: '#e8eaf0', size: 14 },
        },
        paper_bgcolor: '#1e2230',
        plot_bgcolor: '#1a1d27',
        font: { color: '#9ba3b5', family: 'Inter' },
        xaxis: {
            title: 'Distancia (m)',
            gridcolor: '#2d3348',
            zerolinecolor: '#3d4565',
        },
        yaxis: {
            title: 'Elevación (m)',
            gridcolor: '#2d3348',
            zerolinecolor: '#3d4565',
            scaleanchor: 'x',
            scaleratio: 1,
        },
        legend: {
            orientation: 'h',
            y: -0.15,
            font: { size: 11 },
        },
        margin: { l: 60, r: 20, t: 40, b: 60 },
        height: 500,
        dragmode: 'pan',
        hovermode: 'closest',
    }), [profileData]);

    // Handle point drag via plotly_relayout
    const handleRelayout = useCallback((eventData) => {
        // Plotly fires relayout events when points are moved in editable mode
        // but we use a different approach: click to select, then move
    }, []);

    // Drag state
    const [dragState, setDragState] = useState(null); // { traceIdx, pointIdx, type }

    const handleClick = useCallback((event) => {
        if (!event.points || event.points.length === 0) return;
        const point = event.points[0];

        // Only allow clicking on crest/toe traces (indices 4 and 5)
        const traceIdx = point.curveNumber;
        if (traceIdx < 4 || traceIdx > 5) return;

        const type = traceIdx === 4 ? 'crest' : 'toe';
        const benchIdx = point.pointIndex;

        setDragState({ type, benchIdx, active: true });
    }, []);

    // Handle chart click to move a selected point
    const handleChartClick = useCallback((event) => {
        if (!dragState?.active || !event.points) return;

        // Get the clicked position on chart
        const x = event.points[0]?.x;
        const y = event.points[0]?.y;
        if (x == null || y == null) return;

        const newBenches = [...benches].map(b => ({ ...b }));
        const b = newBenches[dragState.benchIdx];

        if (dragState.type === 'crest') {
            b.crest_distance = x;
            b.crest_elevation = y;
        } else {
            b.toe_distance = x;
            b.toe_elevation = y;
        }

        // Recalculate derived values
        b.bench_height = Math.abs(b.crest_elevation - b.toe_elevation);
        const dx = b.toe_distance - b.crest_distance;
        const dz = b.crest_elevation - b.toe_elevation;
        b.face_angle = Math.abs(dx) > 0.01
            ? Math.abs(Math.atan2(dz, Math.abs(dx)) * 180 / Math.PI)
            : 90;

        setDraggedBenches(newBenches);
        setDragState(null);
    }, [dragState, benches]);

    // Save edited benchhes to API
    const handleSave = useCallback(async () => {
        if (!draggedBenches) return;
        setSaving(true);
        try {
            const res = await updateReconciled(sectionIndex, draggedBenches);
            onBenchUpdate?.(res.data);
            setDraggedBenches(null);
        } catch (err) {
            console.error('Save failed:', err);
        }
        setSaving(false);
    }, [draggedBenches, sectionIndex, onBenchUpdate]);

    const handleReset = useCallback(() => {
        setDraggedBenches(null);
        setDragState(null);
    }, []);

    if (!profileData) {
        return (
            <div className="empty-state">
                <div className="icon">📐</div>
                <p>Selecciona una sección para ver su perfil</p>
            </div>
        );
    }

    return (
        <div>
            <div className="chart-container">
                {dragState?.active && (
                    <div className="drag-hint" style={{ color: '#f59e0b' }}>
                        🖱️ Click en el gráfico para mover {dragState.type === 'crest' ? 'Cresta' : 'Pie'} B{benches[dragState.benchIdx]?.bench_number} — ESC para cancelar
                    </div>
                )}
                {!dragState?.active && benches.length > 0 && (
                    <div className="drag-hint">
                        Click en ▲ o ▼ para mover un punto
                    </div>
                )}
                <Plot
                    data={traces}
                    layout={layout}
                    config={{
                        responsive: true,
                        displayModeBar: true,
                        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
                    }}
                    onClick={dragState?.active ? handleChartClick : handleClick}
                    onRelayout={handleRelayout}
                    style={{ width: '100%' }}
                />
            </div>

            {/* Edit controls */}
            {draggedBenches && (
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary btn-sm" onClick={handleReset}>
                        ↩ Deshacer cambios
                    </button>
                    <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving}>
                        {saving ? <span className="spinner" /> : null}
                        💾 Guardar y recalcular
                    </button>
                </div>
            )}

            {/* Bench parameters table */}
            {benches.length > 0 && (
                <div className="card" style={{ marginTop: '1rem' }}>
                    <div className="card-header">
                        <h3>📊 Parámetros de Bancos — {profileData.section_name}</h3>
                        {draggedBenches && (
                            <span className="badge badge-warning">Editado</span>
                        )}
                    </div>
                    <div className="card-body" style={{ padding: 0, overflow: 'auto' }}>
                        <table className="bench-table">
                            <thead>
                                <tr>
                                    <th>Banco</th>
                                    <th>Cresta (d, z)</th>
                                    <th>Pie (d, z)</th>
                                    <th>Altura (m)</th>
                                    <th>Ángulo (°)</th>
                                    <th>Berma (m)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {benches.map((b, i) => (
                                    <tr key={i}>
                                        <td>B{b.bench_number}</td>
                                        <td>{b.crest_distance?.toFixed(1)}, {b.crest_elevation?.toFixed(1)}</td>
                                        <td>{b.toe_distance?.toFixed(1)}, {b.toe_elevation?.toFixed(1)}</td>
                                        <td>{b.bench_height?.toFixed(1)}</td>
                                        <td>{b.face_angle?.toFixed(1)}</td>
                                        <td>{b.berm_width?.toFixed(1)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
