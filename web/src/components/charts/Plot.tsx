import createPlotlyComponent from 'react-plotly.js/factory';
import Plotly from 'plotly.js/dist/plotly-cartesian.min.js';
import spanishLocale from 'plotly.js/lib/locales/es.js';
import { createElement, useMemo, type ComponentProps } from 'react';
import type { Layout } from 'plotly.js';
import { useTheme } from '../../stores/theme';
import { readThemeColor, resolveThemeVariables } from '../../utils/theme';

Plotly.register(spanishLocale);

const Plot = createPlotlyComponent(Plotly);

export default function ThemedPlot(props: ComponentProps<typeof Plot>) {
  const isDark = useTheme((s) => s.isDark);
  const layout = useMemo(() => {
    const resolved = resolveThemeVariables(props.layout ?? {}) as Partial<Layout>;
    const grid = readThemeColor('--color-border', 'transparent');
    return {
      ...resolved,
      font: { color: readThemeColor('--color-text-primary', 'currentColor'), ...resolved.font },
      xaxis: { gridcolor: grid, zerolinecolor: grid, ...resolved.xaxis },
      yaxis: { gridcolor: grid, zerolinecolor: grid, ...resolved.yaxis },
    };
  }, [props.layout, isDark]);

  return createElement(Plot, { ...props, layout });
}
