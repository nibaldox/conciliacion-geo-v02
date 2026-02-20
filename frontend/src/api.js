import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE,
    timeout: 120000,
});

export const health = () => api.get('/api/health');

// ── Mesh Upload ──
export const uploadDesign = (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/api/upload/design', fd);
};

export const uploadTopo = (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/api/upload/topo', fd);
};

// ── Mesh Data ──
export const getMeshBounds = () => api.get('/api/mesh/bounds');

// ── Section Generation (4 methods, matching Streamlit) ──

// Method 1: From DXF/CSV file (perpendicular sections)
export const sectionsFromFile = (file, spacing, length, sector, azMode) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('spacing', spacing);
    fd.append('length', length);
    fd.append('sector', sector);
    fd.append('az_mode', azMode);
    return api.post('/api/sections/from-file', fd);
};

// Method 2: Interactive click on plan view
export const addSectionClick = (origin, length, sector, azMode, azimuth) =>
    api.post('/api/sections/add-click', { origin, length, sector, az_mode: azMode, azimuth });

// Method 3: Manual definition
export const sectionsManual = (sectionsData) =>
    api.post('/api/sections/manual', sectionsData);

// Method 4: Automatic along crest line
export const sectionsAuto = (start, end, nSections, length, sector, azMethod, fixedAz) =>
    api.post('/api/sections/auto', {
        start, end, n_sections: nSections, length, sector, az_method: azMethod, fixed_az: fixedAz,
    });

export const getSections = () => api.get('/api/sections');
export const clearSections = () => api.delete('/api/sections');

// ── Settings ──
export const updateSettings = (settings) =>
    api.post('/api/settings', settings);

export const updateTolerances = (tolerances) =>
    api.post('/api/tolerances', tolerances);

// ── Processing ──
export const processAll = () => api.post('/api/process');

// ── Profile Data ──
export const getProfile = (sectionIndex) =>
    api.get(`/api/profiles/${sectionIndex}`);

// ── Interactive Edit ──
export const updateReconciled = (sectionIndex, benches) =>
    api.put(`/api/reconciled/${sectionIndex}`, benches);

// ── Results ──
export const getResults = () => api.get('/api/results');

// ── Export ──
export const exportExcel = () =>
    api.get('/api/export/excel', { responseType: 'blob' });

export const exportDxf = () =>
    api.get('/api/export/dxf', { responseType: 'blob' });
