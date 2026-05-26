import { useState, useCallback, useEffect } from 'react';
import './index.css';
import ProfileChart from './components/ProfileChart';
import PlanView from './components/PlanView';
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
  const [sectionTab, setSectionTab] = useState('file');

  // Upload file names
  const [files, setFiles] = useState({ design: null, topo: null });

  // Mesh data for plan view
  const [meshData, setMeshData] = useState(null);

  // Settings
  const [settings, setSettings] = useState({
    resolution: 0.5,
    face_threshold: 40,
    berm_threshold: 5,
  });

  // Section generation parameters
  const [secParams, setSecParams] = useState({
    spacing: 20,
    length: 200,
    sector: 'Principal',
    azMode: 'perpendicular',
    // auto tab
    startX: 0, startY: 0, endX: 0, endY: 0,
    nSections: 5,
    azMethod: 'perpendicular',
    fixedAz: 0,
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
    setLoading(`Cargando ${type === 'design' ? 'diseño' : 'topografía'}...`);
    try {
      if (type === 'design') {
        await api.uploadDesign(file);
        setFiles(f => ({ ...f, design: file.name }));
      } else {
        await api.uploadTopo(file);
        setFiles(f => ({ ...f, topo: file.name }));
      }
      const h = await api.health();
      setStatus(h.data);
      // Load mesh data for plan view if design is loaded
      if (type === 'design' || h.data.has_design) {
        try {
          const m = await api.getMeshBounds();
          setMeshData(m.data);
          // Update auto tab defaults from bounds
          const b = m.data.bounds;
          setSecParams(p => ({
            ...p,
            startX: b.xmin, startY: b.center[1],
            endX: b.xmax, endY: b.center[1],
          }));
        } catch { }
      }
      showToast(`${file.name} cargado`);
    } catch (err) {
      showToast(`Error: ${err.response?.data?.detail || err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Section generation from file (CSV/DXF) ──
  const handleFileSection = useCallback(async (file) => {
    setLoading('Generando secciones desde archivo...');
    try {
      const res = await api.sectionsFromFile(
        file, secParams.spacing, secParams.length, secParams.sector, secParams.azMode
      );
      setSections(res.data.sections);
      showToast(`${res.data.n_sections} secciones generadas`);
    } catch (err) {
      showToast(`Error: ${err.response?.data?.detail || err.message}`, 'error');
    }
    setLoading('');
  }, [secParams]);

  // ── Auto section generation ──
  const handleAutoSections = useCallback(async () => {
    setLoading('Generando secciones automáticas...');
    try {
      const res = await api.sectionsAuto(
        [secParams.startX, secParams.startY],
        [secParams.endX, secParams.endY],
        secParams.nSections,
        secParams.length,
        secParams.sector,
        secParams.azMethod,
        secParams.fixedAz
      );
      setSections(res.data.sections);
      showToast(`${res.data.sections.length} secciones generadas`);
    } catch (err) {
      showToast(`Error: ${err.response?.data?.detail || err.message}`, 'error');
    }
    setLoading('');
  }, [secParams]);

  // ── Process ──
  const handleProcess = useCallback(async () => {
    setLoading('Cortando superficies y extrayendo parámetros...');
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
    setActiveTab('profile');
    setLoading('Cargando perfil...');
    try {
      const r = await api.getProfile(idx);
      setProfileData(r.data);
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Section added via click ──
  const handleSectionAdded = useCallback(async () => {
    const res = await api.getSections();
    setSections(res.data);
  }, []);

  // ── Clear sections ──
  const handleClearSections = useCallback(async () => {
    await api.clearSections();
    setSections([]);
    setSelectedSection(null);
    setProfileData(null);
  }, []);

  // ── Export ──
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
      showToast(`Error: ${err.message}`, 'error');
    }
    setLoading('');
  }, []);

  // ── Compliance map ──
  const sectionCompliance = {};
  results.forEach(c => {
    const sec = c.section;
    if (!sectionCompliance[sec]) sectionCompliance[sec] = 'CUMPLE';
    const statuses = [c.height_status, c.angle_status, c.berm_status];
    if (statuses.includes('NO CUMPLE')) sectionCompliance[sec] = 'NO CUMPLE';
    else if (statuses.includes('FUERA DE TOLERANCIA') && sectionCompliance[sec] !== 'NO CUMPLE')
      sectionCompliance[sec] = 'FUERA DE TOLERANCIA';
  });

  // Stats
  const total = results.length;
  const cumpleH = results.filter(r => r.height_status === 'CUMPLE').length;
  const cumpleA = results.filter(r => r.angle_status === 'CUMPLE').length;
  const cumpleB = results.filter(r => r.berm_status === 'CUMPLE').length;

  const canProcess = status.has_design && status.has_topo && sections.length > 0;

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
          <h3>📁 Superficies</h3>
          <UploadZone label="Diseño (STL/OBJ/DXF)" icon="🔷" filename={files.design} accept=".stl,.obj,.ply,.dxf" onFile={(f) => handleUpload('design', f)} />
          <div style={{ height: '0.5rem' }} />
          <UploadZone label="Topografía (STL/OBJ/DXF)" icon="🟢" filename={files.topo} accept=".stl,.obj,.ply,.dxf" onFile={(f) => handleUpload('topo', f)} />
        </div>

        {/* Settings */}
        <div className="sidebar-section">
          <h3>⚙️ Detección de Bancos</h3>
          <SliderInput label="Resolución (m)" value={settings.resolution} min={0.1} max={2} step={0.1}
            onChange={v => setSettings(s => ({ ...s, resolution: v }))} />
          <SliderInput label="Áng. mín. cara (°)" value={settings.face_threshold} min={0} max={90} step={1}
            onChange={v => setSettings(s => ({ ...s, face_threshold: v }))} />
          <SliderInput label="Áng. máx. berma (°)" value={settings.berm_threshold} min={0} max={10} step={1}
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
                  <li key={i} className={`section-item ${selectedSection === i ? 'active' : ''}`} onClick={() => handleSelectSection(i)}>
                    <div>
                      <div className="name">{sec.name}</div>
                      <div className="sector">{sec.sector}</div>
                    </div>
                    {comp && <StatusBadge status={comp} />}
                  </li>
                );
              })}
            </ul>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button className="btn btn-primary btn-sm" style={{ flex: 1 }} disabled={!canProcess || !!loading} onClick={handleProcess}>
                ⚡ Procesar
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleClearSections}>🗑️</button>
            </div>
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
        {total > 0 && (
          <div className="stats-grid">
            <div className="stat-card blue">
              <div className="value">{total}</div>
              <div className="label">Bancos Analizados</div>
            </div>
            <div className="stat-card green">
              <div className="value">{total > 0 ? `${Math.round(cumpleH / total * 100)}%` : '-'}</div>
              <div className="label">Cumple Altura</div>
            </div>
            <div className="stat-card green">
              <div className="value">{total > 0 ? `${Math.round(cumpleA / total * 100)}%` : '-'}</div>
              <div className="label">Cumple Ángulo</div>
            </div>
            <div className="stat-card green">
              <div className="value">{total > 0 ? `${Math.round(cumpleB / total * 100)}%` : '-'}</div>
              <div className="label">Cumple Berma</div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="tabs">
          {status.has_design && (
            <div className={`tab ${activeTab === 'sections' ? 'active' : ''}`} onClick={() => setActiveTab('sections')}>
              📐 Definir Secciones
            </div>
          )}
          <div className={`tab ${activeTab === 'profile' ? 'active' : ''}`} onClick={() => setActiveTab('profile')}>
            📈 Perfil Interactivo
          </div>
          {results.length > 0 && (
            <div className={`tab ${activeTab === 'results' ? 'active' : ''}`} onClick={() => setActiveTab('results')}>
              📊 Resultados
            </div>
          )}
        </div>

        {/* ── SECTIONS TAB ── */}
        {activeTab === 'sections' && (
          <div>
            {/* Sub-tabs matching Streamlit's 4 methods */}
            <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1rem' }}>
              {[
                { id: 'file', label: '📂 Archivo (CSV/DXF)' },
                { id: 'click', label: '🗺️ Interactivo' },
                { id: 'auto', label: '🔄 Automático' },
              ].map(t => (
                <button key={t.id} className={`btn btn-sm ${sectionTab === t.id ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSectionTab(t.id)}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* File tab */}
            {sectionTab === 'file' && (
              <div className="card">
                <div className="card-header"><h3>📂 Generar Secciones desde Archivo de Coordenadas</h3></div>
                <div className="card-body">
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                    Carga un <strong>CSV</strong> (columnas X, Y) o <strong>DXF</strong> (Polyline/LWPolyline).
                    Las secciones se generarán perpendiculares a cada segmento de la línea.
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                    <NumberInput label="Distancia entre perfiles (m)" value={secParams.spacing}
                      onChange={v => setSecParams(p => ({ ...p, spacing: v }))} />
                    <NumberInput label="Longitud de sección (m)" value={secParams.length}
                      onChange={v => setSecParams(p => ({ ...p, length: v }))} />
                    <TextInput label="Sector" value={secParams.sector}
                      onChange={v => setSecParams(p => ({ ...p, sector: v }))} />
                    <SelectInput label="Azimut" value={secParams.azMode}
                      options={[
                        { value: 'perpendicular', label: 'Perpendicular (Recomendado)' },
                        { value: 'local_slope', label: 'Auto (pend. local)' },
                      ]}
                      onChange={v => setSecParams(p => ({ ...p, azMode: v }))} />
                  </div>
                  <UploadZone label="Cargar coordenadas (CSV, DXF)" icon="📎" accept=".csv,.txt,.dxf"
                    onFile={handleFileSection} />
                </div>
              </div>
            )}

            {/* Interactive click tab */}
            {sectionTab === 'click' && (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                  <NumberInput label="Longitud de sección (m)" value={secParams.length}
                    onChange={v => setSecParams(p => ({ ...p, length: v }))} />
                  <TextInput label="Sector" value={secParams.sector}
                    onChange={v => setSecParams(p => ({ ...p, sector: v }))} />
                  <SelectInput label="Azimut" value={secParams.azMode === 'local_slope' ? 'auto' : secParams.azMode}
                    options={[
                      { value: 'auto', label: 'Auto (pend. local)' },
                      { value: 'manual', label: 'Manual' },
                    ]}
                    onChange={v => setSecParams(p => ({ ...p, azMode: v }))} />
                </div>
                <PlanView
                  meshData={meshData}
                  sections={sections}
                  onSectionAdded={handleSectionAdded}
                  settings={{ length: secParams.length, sector: secParams.sector, azMode: secParams.azMode }}
                />
              </div>
            )}

            {/* Auto tab */}
            {sectionTab === 'auto' && (
              <div className="card">
                <div className="card-header"><h3>🔄 Secciones Automáticas a lo Largo de una Línea</h3></div>
                <div className="card-body">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                    <NumberInput label="Inicio X" value={secParams.startX} onChange={v => setSecParams(p => ({ ...p, startX: v }))} />
                    <NumberInput label="Inicio Y" value={secParams.startY} onChange={v => setSecParams(p => ({ ...p, startY: v }))} />
                    <NumberInput label="Fin X" value={secParams.endX} onChange={v => setSecParams(p => ({ ...p, endX: v }))} />
                    <NumberInput label="Fin Y" value={secParams.endY} onChange={v => setSecParams(p => ({ ...p, endY: v }))} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                    <NumberInput label="N° secciones" value={secParams.nSections} onChange={v => setSecParams(p => ({ ...p, nSections: v }))} />
                    <NumberInput label="Longitud (m)" value={secParams.length} onChange={v => setSecParams(p => ({ ...p, length: v }))} />
                    <TextInput label="Sector" value={secParams.sector} onChange={v => setSecParams(p => ({ ...p, sector: v }))} />
                    <SelectInput label="Azimut" value={secParams.azMethod}
                      options={[
                        { value: 'perpendicular', label: 'Perpendicular (Recomendado)' },
                        { value: 'fixed', label: 'Fijo' },
                        { value: 'local_slope', label: 'Auto (pend. local)' },
                      ]}
                      onChange={v => setSecParams(p => ({ ...p, azMethod: v }))} />
                  </div>
                  {secParams.azMethod === 'fixed' && (
                    <NumberInput label="Azimut fijo (°)" value={secParams.fixedAz}
                      onChange={v => setSecParams(p => ({ ...p, fixedAz: v }))} />
                  )}
                  <button className="btn btn-primary" onClick={handleAutoSections} disabled={!!loading}>
                    🔄 Generar Secciones Automáticas
                  </button>
                </div>
              </div>
            )}

            {/* Plan view with sections if we have sections */}
            {sectionTab !== 'click' && meshData && sections.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <PlanView meshData={meshData} sections={sections} settings={secParams} />
              </div>
            )}
          </div>
        )}

        {/* ── PROFILE TAB ── */}
        {activeTab === 'profile' && (
          <ProfileChart
            profileData={profileData}
            sectionIndex={selectedSection}
            onBenchUpdate={() => {
              if (selectedSection != null) {
                api.getProfile(selectedSection).then(r => setProfileData(r.data));
                api.getResults().then(r => setResults(r.data));
              }
            }}
          />
        )}

        {/* ── RESULTS TAB ── */}
        {activeTab === 'results' && results.length > 0 && (
          <div className="card">
            <div className="card-header"><h3>📊 Tabla de Resultados Completa</h3></div>
            <div className="card-body" style={{ padding: 0, maxHeight: '600px', overflow: 'auto' }}>
              <table className="bench-table">
                <thead>
                  <tr>
                    <th>Sección</th><th>Banco</th>
                    <th>H. Diseño</th><th>H. Real</th><th>Cumpl. H</th>
                    <th>Áng. Diseño</th><th>Áng. Real</th><th>Cumpl. Á</th>
                    <th>Berma</th><th>Cumpl. B</th>
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
        {!status.has_design && (
          <div className="empty-state">
            <div className="icon">⛏️</div>
            <p>Carga las superficies STL para comenzar el análisis</p>
          </div>
        )}
      </main>

      {/* Toast */}
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}
    </div>
  );
}

// ── Sub-components ──

function UploadZone({ label, icon, filename, accept, onFile }) {
  return (
    <label className={`upload-zone ${filename ? 'active' : ''}`}>
      <input type="file" accept={accept} style={{ display: 'none' }}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
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
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent-blue)' }} />
    </div>
  );
}

function NumberInput({ label, value, onChange }) {
  return (
    <div>
      <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{label}</label>
      <input type="number" value={value} onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        style={{
          width: '100%', padding: '0.4rem 0.5rem', background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)',
          fontFamily: 'JetBrains Mono', fontSize: '0.85rem',
        }} />
    </div>
  );
}

function TextInput({ label, value, onChange }) {
  return (
    <div>
      <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{label}</label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%', padding: '0.4rem 0.5rem', background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)',
          fontSize: '0.85rem',
        }} />
    </div>
  );
}

function SelectInput({ label, value, options, onChange }) {
  return (
    <div>
      <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%', padding: '0.4rem 0.5rem', background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)',
          fontSize: '0.85rem',
        }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function StatusBadge({ status }) {
  const cls = status === 'CUMPLE' ? 'badge-success' : status === 'NO CUMPLE' ? 'badge-danger' : 'badge-warning';
  const txt = status === 'CUMPLE' ? '✓' : status === 'NO CUMPLE' ? '✗' : '!';
  return <span className={`badge ${cls}`}>{txt}</span>;
}

export default App;
