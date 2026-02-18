import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE,
    timeout: 120000,
});

export const health = () => api.get('/api/health');

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

export const loadSections = (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/api/sections/load', fd);
};

export const getSections = () => api.get('/api/sections');

export const updateSettings = (settings) =>
    api.post('/api/settings', settings);

export const updateTolerances = (tolerances) =>
    api.post('/api/tolerances', tolerances);

export const processAll = () => api.post('/api/process');

export const getProfile = (sectionIndex) =>
    api.get(`/api/profiles/${sectionIndex}`);

export const updateReconciled = (sectionIndex, benches) =>
    api.put(`/api/reconciled/${sectionIndex}`, benches);

export const getResults = () => api.get('/api/results');

export const exportExcel = () =>
    api.get('/api/export/excel', { responseType: 'blob' });

export const exportDxf = () =>
    api.get('/api/export/dxf', { responseType: 'blob' });
