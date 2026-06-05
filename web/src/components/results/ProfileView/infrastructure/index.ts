// Infrastructure barrel
export {
  useProfileQuery,
  useSectionsQuery,
  useComparisonsQuery,
  useSelectedSectionMeta,
  useSessionMeshCount,
  useQuery,
} from './apiAdapter';
export {
  createPlotlyConfig,
  createPlotlyLayout,
  designLineStyle,
  topoLineStyle,
  reconciledLineStyle,
  benchMarkerStyle,
} from './plotlyTheme';
export {
  writeFiltersToUrl,
  readFiltersFromUrl,
  readCrossLink,
  writeCrossLink,
  readFiltersFromStorage,
  writeFiltersToStorage,
} from './persistenceAdapter';
export type { CrossLinkPersisted } from './persistenceAdapter';
