import { useState, useMemo, useCallback } from 'react';
import Plot from 'react-plotly.js';
import * as api from '../api';

/**
 * Plan view scatter plot of the design mesh, with section lines overlaid.
 * Click on the plot to add a new section (interactive mode).
 */
export default function PlanView({ meshData, sections, onSectionAdded, settings }) {
    const [clickMode, setClickMode] = useState(false);

    const traces = useMemo(() => {
        const t = [];

        // 1. Mesh vertices scatter
        if (meshData?.vertices) {
            t.push({
                x: meshData.vertices.x,
                y: meshData.vertices.y,
                mode: 'markers',
                marker: {
                    size: 2,
                    color: meshData.vertices.z,
                    colorscale: 'Earth',
                    showscale: true,
                    colorbar: { title: 'Elev (m)', thickness: 12, len: 0.5 },
                },
                name: 'Diseño',
                hovertemplate: 'E: %{x:.1f}<br>N: %{y:.1f}<extra></extra>',
            });
        }

        // 2. Section lines
        if (sections) {
            sections.forEach((sec) => {
                const az = (sec.azimuth * Math.PI) / 180;
                const dx = Math.sin(az);
                const dy = Math.cos(az);
                const half = sec.length / 2;
                const ox = sec.origin[0];
                const oy = sec.origin[1];

                t.push({
                    x: [ox - dx * half, ox, ox + dx * half],
                    y: [oy - dy * half, oy, oy + dy * half],
                    mode: 'lines+markers+text',
                    text: ['', sec.name, ''],
                    textposition: 'top center',
                    textfont: { size: 9, color: '#ef4444' },
                    line: { color: '#ef4444', width: 2.5 },
                    marker: { size: [4, 8, 4], color: '#ef4444' },
                    showlegend: false,
                    hoverinfo: 'text',
                    hovertext: `${sec.name} — Az: ${sec.azimuth}°`,
                });
            });
        }

        return t;
    }, [meshData, sections]);

    const layout = useMemo(() => ({
        paper_bgcolor: '#1e2230',
        plot_bgcolor: '#1a1d27',
        font: { color: '#9ba3b5', family: 'Inter' },
        xaxis: { title: 'Este (m)', gridcolor: '#2d3348' },
        yaxis: { title: 'Norte (m)', gridcolor: '#2d3348', scaleanchor: 'x', scaleratio: 1 },
        height: 500,
        margin: { l: 60, r: 20, t: 10, b: 40 },
        dragmode: clickMode ? 'select' : 'pan',
        hovermode: 'closest',
    }), [clickMode]);

    const handleClick = useCallback(async (event) => {
        if (!clickMode || !event.points?.length) return;
        const { x, y } = event.points[0];
        try {
            const res = await api.addSectionClick(
                [x, y],
                settings.length || 200,
                settings.sector || '',
                settings.azMode || 'auto',
                settings.azimuth || 0
            );
            onSectionAdded?.(res.data);
        } catch (err) {
            console.error('Error adding section:', err);
        }
    }, [clickMode, settings, onSectionAdded]);

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                <button
                    className={`btn btn-sm ${clickMode ? 'btn-danger' : 'btn-secondary'}`}
                    onClick={() => setClickMode(!clickMode)}
                >
                    {clickMode ? '✋ Dejar de agregar' : '📌 Click para agregar secciones'}
                </button>
                {clickMode && (
                    <span style={{ fontSize: '0.8rem', color: 'var(--accent-yellow)' }}>
                        Haz click sobre la vista de planta para agregar secciones
                    </span>
                )}
            </div>
            <div className="chart-container">
                <Plot
                    data={traces}
                    layout={layout}
                    config={{ responsive: true, displayModeBar: true }}
                    onClick={handleClick}
                    style={{ width: '100%' }}
                />
            </div>
        </div>
    );
}
