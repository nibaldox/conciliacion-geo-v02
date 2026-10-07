declare module 'plotly.js/dist/plotly-cartesian.min.js' {
  import type * as Plotly from 'plotly.js';

  const plotly: typeof Plotly;
  export default plotly;
}

declare module 'plotly.js/lib/locales/es.js' {
  import type { PlotlyModule } from 'plotly.js';

  const locale: PlotlyModule;
  export default locale;
}
