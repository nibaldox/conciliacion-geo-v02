"""Pure Plotly trace builder for spill (derrame) areas.

No Streamlit calls.
"""
import numpy as np
import plotly.graph_objects as go


def add_spill_areas_traces(fig, benches, pt_prof):
    legend_added = False
    for bench in benches:
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

                fig.add_trace(go.Scatter(
                    x=poly_x, y=poly_y,
                    fill='toself', fillcolor='rgba(255, 165, 0, 0.4)',
                    line=dict(width=0),
                    name='Derrame',
                    hoverinfo='skip',
                    showlegend=not legend_added
                ))
                legend_added = True
