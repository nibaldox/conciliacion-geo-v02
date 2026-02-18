import { useState, useCallback, useEffect } from 'react';
import './index.css';
import ProfileChart from './components/ProfileChart';
import * as api from './api';

function App() {
  // ── State ──
  const [status, setStatus] = useState({ has_design: false, has_topo: false, n_sections: 0, n_results: 0 });
  const [sections, setSections] = useState([]);
  const [selectedSection, setSelectedSection] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState('');
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState('profile');

  // Upload file names for display
  const [files, setFiles] = useState({ design: null, topo: null, sections: null });

  // Settings
  const [settings, setSettings] = useState({
    resolution: 0.5,
    face_threshold: 40,
    berm_threshold: 20,
  });

  // ── Toast helper ──
  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  // ── Fetch health on mount ──
  useEffect(() => {
    api.health().then(r => setStatus(r.data)).catch(() => { });
  }, []);

  // ── Upload handlers ──
  const handleUpload = useCallback(async (type, file) => {
    setLoading(`Cargando ${type}...`);
    try {
      if (type === 'design') {
        await api.uploadDesign(file);
        setFiles(f => ({ ...f, design: file.name }));
      } else if (type === 'topo') {
        await api.uploadTopo(file);
        setFiles(f => ({ ...f, topo: file.name }));
      } else if (type === 'sections') {
        await api.loadSections(file);
        setFiles(f => ({ ...f, sections: file.name }));
        const res = await api.getSections();
        setSections(res.data);
      }
      const h = await api.health();
      setStatus(h.data);
      showToast(`${type} cargado correctamente`);
    } catch (err) {
      showToast(`Error: ${err.response?.data?.detail || err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Process ──
  const handleProcess = useCallback(async () => {
    setLoading('Procesando secciones...');
    try {
      await api.updateSettings(settings);
      await api.processAll();
      const h = await api.health();
      setStatus(h.data);
      const r = await api.getResults();
      setResults(r.data);
      showToast(`${h.data.n_results} resultados generados`);
    } catch (err) {
      showToast(`Error: ${err.response?.data?.detail || err.message}`, 'error');
    }
    setLoading('');
  }, [settings]);

  // ── Load profile when section selected ──
  const handleSelectSection = useCallback(async (idx) => {
    setSelectedSection(idx);
    setLoading('Cargando perfil...');
    try {
      const r = await api.getProfile(idx);
      setProfileData(r.data);
    } catch (err) {
      showToast(`Error cargando perfil: ${err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Export handlers ──
  const handleExport = useCallback(async (type) => {
    setLoading(`Exportando ${type}...`);
    try {
      const res = type === 'excel' ? await api.exportExcel() : await api.exportDxf();
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = type === 'excel' ? 'Conciliacion_Geotecnica.xlsx' : 'Perfiles_3D.dxf';
      a.click();
      URL.revokeObjectURL(url);
      showToast(`${type.toUpperCase()} descargado`);
    } catch (err) {
      showToast(`Error exportando: ${err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Section compliance map ──
  const sectionCompliance = {};
  results.forEach(c => {
    const sec = c.section;
    if (!sectionCompliance[sec]) sectionCompliance[sec] = 'CUMPLE';
    const statuses = [c.height_status, c.angle_status, c.berm_status];
    if (statuses.includes('NO CUMPLE')) sectionCompliance[sec] = 'NO CUMPLE';
    else if (statuses.includes('FUERA DE TOLERANCIA') && sectionCompliance[sec] !== 'NO CUMPLE')
      sectionCompliance[sec] = 'FUERA DE TOLERANCIA';
  });

  // ── Stats ──
  const totalResults = results.length;
  const cumpleH = results.filter(r => r.height_status === 'CUMPLE').length;
  const cumpleA = results.filter(r => r.angle_status === 'CUMPLE').length;
  const cumpleB = results.filter(r => r.berm_status === 'CUMPLE').length;

  const canProcess = status.has_design && status.has_topo && status.n_sections > 0;

  return (
    <div className="app-layout">
      {/* ── Header ── */}
      <header className="app-header">
        <span style={{ fontSize: '1.4rem' }}>⛏️</span>
        <h1>Conciliación Geotécnica</h1>
        <span className="version">v2.0 React</span>
        <div style={{ flex: 1 }} />
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-cyan)', fontSize: '0.85rem' }}>
            <span className="spinner" />
            {loading}
          </div>
        )}
      </header>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        {/* Upload */}
        <div className="sidebar-section">
          <h3>📁 Archivos</h3>
          <UploadZone
            label="Superficie Diseño (.stl)"
            icon="🔷"
            filename={files.design}
            accept=".stl"
            onFile={(f) => handleUpload('design', f)}
          />
          <div style={{ height: '0.5rem' }} />
          <UploadZone
            label="Superficie Topo (.stl)"
            icon="🟢"
            filename={files.topo}
            accept=".stl"
            onFile={(f) => handleUpload('topo', f)}
          />
          <div style={{ height: '0.5rem' }} />
          <UploadZone
            label="Secciones (.json)"
            icon="📐"
            filename={files.sections}
            accept=".json"
            onFile={(f) => handleUpload('sections', f)}
          />
        </div>

        {/* Process */}
        <div className="sidebar-section">
          <button
            className="btn btn-primary btn-block"
            disabled={!canProcess || !!loading}
            onClick={handleProcess}
          >
            ⚡ Procesar Todo
          </button>
        </div>

        {/* Settings */}
        <div className="sidebar-section">
          <h3>⚙️ Configuración</h3>
          <SliderInput label="Resolución (m)" value={settings.resolution} min={0.1} max={2} step={0.1}
            onChange={v => setSettings(s => ({ ...s, resolution: v }))} />
          <SliderInput label="Áng. mín. cara (°)" value={settings.face_threshold} min={0} max={90} step={1}
            onChange={v => setSettings(s => ({ ...s, face_threshold: v }))} />
          <SliderInput label="Áng. máx. berma (°)" value={settings.berm_threshold} min={5} max={30} step={1}
            onChange={v => setSettings(s => ({ ...s, berm_threshold: v }))} />
        </div>

        {/* Sections list */}
        {sections.length > 0 && (
          <div className="sidebar-section">
            <h3>📋 Secciones ({sections.length})</h3>
            <ul className="section-list">
              {sections.map((sec, i) => {
                const comp = sectionCompliance[sec.name];
                return (
                  <li
                    key={i}
                    className={`section-item ${selectedSection === i ? 'active' : ''}`}
                    onClick={() => handleSelectSection(i)}
                  >
                    <div>
                      <div className="name">{sec.name}</div>
                      <div className="sector">{sec.sector}</div>
                    </div>
                    {comp && (
                      <span className={`badge ${comp === 'CUMPLE' ? 'badge-success' : comp === 'NO CUMPLE' ? 'badge-danger' : 'badge-warning'}`}>
                        {comp === 'CUMPLE' ? '✓' : comp === 'NO CUMPLE' ? '✗' : '!'}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Export */}
        {results.length > 0 && (
          <div className="sidebar-section">
            <h3>📥 Exportar</h3>
            <button className="btn btn-secondary btn-block btn-sm" onClick={() => handleExport('excel')} style={{ marginBottom: '0.5rem' }}>
              📊 Excel
            </button>
            <button className="btn btn-secondary btn-block btn-sm" onClick={() => handleExport('dxf')}>
              📐 DXF 3D
            </button>
          </div>
        )}
      </aside>

      {/* ── Main Content ── */}
      <main className="main-content">
        {/* Stats bar */}
        {totalResults > 0 && (
          <div className="stats-grid">
            <div className="stat-card blue">
              <div className="value">{totalResults}</div>
              <div className="label">Bancos Analizados</div>
            </div>
            <div className="stat-card green">
              <div className="value">{totalResults > 0 ? `${Math.round(cumpleH / totalResults * 100)}%` : '-'}</div>
              <div className="label">Cumple Altura</div>
            </div>
            <div className="stat-card green">
              <div className="value">{totalResults > 0 ? `${Math.round(cumpleA / totalResults * 100)}%` : '-'}</div>
              <div className="label">Cumple Ángulo</div>
            </div>
            <div className="stat-card green">
              <div className="value">{totalResults > 0 ? `${Math.round(cumpleB / totalResults * 100)}%` : '-'}</div>
              <div className="label">Cumple Berma</div>
            </div>
          </div>
        )}

        {/* Tabs */}
        {profileData && (
          <div className="tabs">
            <div className={`tab ${activeTab === 'profile' ? 'active' : ''}`} onClick={() => setActiveTab('profile')}>
              📈 Perfil Interactivo
            </div>
            <div className={`tab ${activeTab === 'results' ? 'active' : ''}`} onClick={() => setActiveTab('results')}>
              📊 Resultados
            </div>
          </div>
        )}

        {/* Profile tab */}
        {activeTab === 'profile' && (
          <ProfileChart
            profileData={profileData}
            sectionIndex={selectedSection}
            onBenchUpdate={(data) => {
              // Refresh profile data after bench edit
              if (selectedSection != null) {
                api.getProfile(selectedSection).then(r => setProfileData(r.data));
                api.getResults().then(r => setResults(r.data));
              }
            }}
          />
        )}

        {/* Results tab */}
        {activeTab === 'results' && results.length > 0 && (
          <div className="card">
            <div className="card-header">
              <h3>📊 Tabla de Resultados Completa</h3>
            </div>
            <div className="card-body" style={{ padding: 0, maxHeight: '600px', overflow: 'auto' }}>
              <table className="bench-table">
                <thead>
                  <tr>
                    <th>Sección</th>
                    <th>Banco</th>
                    <th>H. Diseño</th>
                    <th>H. Real</th>
                    <th>Cumpl. H</th>
                    <th>Áng. Diseño</th>
                    <th>Áng. Real</th>
                    <th>Cumpl. Á</th>
                    <th>Berma</th>
                    <th>Cumpl. B</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i}>
                      <td>{r.section}</td>
                      <td>B{r.bench_num}</td>
                      <td>{r.height_design?.toFixed(1)}</td>
                      <td>{r.height_real?.toFixed(1)}</td>
                      <td><StatusBadge status={r.height_status} /></td>
                      <td>{r.angle_design?.toFixed(1)}</td>
                      <td>{r.angle_real?.toFixed(1)}</td>
                      <td><StatusBadge status={r.angle_status} /></td>
                      <td>{r.berm_real?.toFixed(1)}</td>
                      <td><StatusBadge status={r.berm_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Initial empty state */}
        {!profileData && !results.length && (
          <div className="empty-state">
            <div className="icon">⛏️</div>
            <p>Carga las superficies STL y el archivo de secciones para comenzar el análisis</p>
          </div>
        )}
      </main>

      {/* Toast */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ── Sub-components ──

function UploadZone({ label, icon, filename, accept, onFile }) {
  return (
    <label className={`upload-zone ${filename ? 'active' : ''}`}>
      <input
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      <div className="icon">{icon}</div>
      <div className="label">{label}</div>
      {filename && <div className="filename">✓ {filename}</div>}
    </label>
  );
}

function SliderInput({ label, value, min, max, step, onChange }) {
  return (
    <div style={{ marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontFamily: 'JetBrains Mono', color: 'var(--accent-cyan)' }}>{value}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent-blue)' }}
      />
    </div>
  );
}

function StatusBadge({ status }) {
  const cls = status === 'CUMPLE' ? 'badge-success' : status === 'NO CUMPLE' ? 'badge-danger' : 'badge-warning';
  const txt = status === 'CUMPLE' ? '✓' : status === 'NO CUMPLE' ? '✗' : '!';
  return <span className={`badge ${cls}`}>{txt}</span>;
}

export default App;
