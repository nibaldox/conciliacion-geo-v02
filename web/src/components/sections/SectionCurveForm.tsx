import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useMeshBreaklines, useCurveSection } from '../../api/hooks';
import { Button } from '../ui/Button';

export function SectionCurveForm({ onRegisterClickHandler }: { onRegisterClickHandler?: (handler: ((x: number, y: number, curveId?: string, pointIndex?: number) => void) | null) => void }) {
  const { t } = useTranslation();
  const designMeshId = useSession((s) => s.designMeshId);
  const { data: contourData } = useMeshBreaklines(designMeshId);
  const mutation = useCurveSection();

  const [spacing, setSpacing] = useState(10);
  const [lengthUp, setLengthUp] = useState(100);
  const [lengthDown, setLengthDown] = useState(100);
  const [sector, setSector] = useState('');
  const selectedCurveId = useSession((s) => s.selectedCurveId);
  const selectedCurvePoints = useSession((s) => s.selectedCurvePoints);
  const setSelectedCurveId = useSession((s) => s.setSelectedCurveId);
  const setSelectedCurvePoints = useSession((s) => s.setSelectedCurvePoints);

  const handleMapClick = useCallback(
    (x: number, y: number, curveId?: string, pointIndex?: number) => {
      if (!curveId) return;

      const session = useSession.getState();
      const currentSelectedCurve = session.selectedCurveId;
      const currentPoints = session.selectedCurvePoints;

      if (!currentSelectedCurve) {
        // Line selection phase
        session.setSelectedCurveId(curveId);
      } else {
        // Point selection phase
        if (curveId !== currentSelectedCurve || pointIndex === undefined) {
          // Blocked, do nothing if they click a different line or no specific point
          return;
        }
        
        // They clicked the correct line. Add point.
        if (currentPoints.length < 2) {
          session.setSelectedCurvePoints([...currentPoints, { curveId, pointIndex, x, y }]);
        } else {
          // Reset to just this point if they already had 2
          session.setSelectedCurvePoints([{ curveId, pointIndex, x, y }]);
        }
      }
    },
    []
  );

  useEffect(() => {
    onRegisterClickHandler?.(handleMapClick);
    return () => {
      onRegisterClickHandler?.(null);
      // Clean up selections when unmounting the form
      useSession.getState().setSelectedCurveId(null);
      useSession.getState().setSelectedCurvePoints([]);
    };
  }, [onRegisterClickHandler, handleMapClick]);

  const handleGenerate = () => {
    if (selectedCurvePoints.length < 2 || !contourData) return;
    
    const p1 = selectedCurvePoints[0];
    const p2 = selectedCurvePoints[1];
    
    // Parse curveId
    const parts = p1.curveId.split('-');
    const elevIdx = parseInt(parts[0], 10);
    const segIdx = parseInt(parts[1], 10);
    
    const segment = contourData.lines[elevIdx].segments[segIdx];
    
    const startIdx = Math.min(p1.pointIndex, p2.pointIndex);
    const endIdx = Math.max(p1.pointIndex, p2.pointIndex);
    
    let points = segment.slice(startIdx, endIdx + 1);
    if (p1.pointIndex > p2.pointIndex) {
      points = points.reverse();
    }

    mutation.mutate({
      points,
      spacing,
      length: lengthUp + lengthDown,
      length_up: lengthUp,
      length_down: lengthDown,
      sector
    }, {
      onSuccess: () => {
        // Reset selection after successful generation
        setSelectedCurveId(null);
        setSelectedCurvePoints([]);
      },
      onError: (err) => {
        console.error("Profile generation mutation failed:", err);
      }
    });
  };

  const isReady = selectedCurvePoints.length === 2 && Math.abs(selectedCurvePoints[0].pointIndex - selectedCurvePoints[1].pointIndex) > 0;
  const p1 = selectedCurvePoints[0];
  const p2 = selectedCurvePoints[1];

  return (
    <div className="space-y-5">
      {/* Instructions */}
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] p-4 rounded-lg">
        <h4 className="text-sm font-semibold mb-2" style={{ color: 'var(--color-text-primary)' }}>¿Cómo generar?</h4>
        <ol className="list-decimal pl-4 text-xs space-y-1" style={{ color: 'var(--color-text-secondary)' }}>
          <li>Haz clic en una <strong style={{ color: 'var(--color-text-primary)' }}>línea de quiebre</strong> en el mapa para seleccionarla.</li>
          <li>Haz clic en el <strong style={{ color: 'var(--color-text-primary)' }}>punto inicial</strong> de la curva.</li>
          <li>Haz clic en el <strong style={{ color: 'var(--color-text-primary)' }}>punto final</strong> de la curva.</li>
        </ol>
      </div>

      {/* Selection Status */}
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] p-4 rounded-lg space-y-2">
        <div className="flex justify-between text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>Línea seleccionada:</span>
          <span className="font-mono" style={{ color: selectedCurveId ? 'var(--color-text-primary)' : 'var(--color-text-muted)' }}>
            {selectedCurveId || 'Ninguna'}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>Punto Inicial:</span>
          <span className="font-mono" style={{ color: p1 ? 'var(--color-accent)' : 'var(--color-text-muted)' }}>
            {p1 ? `P${p1.pointIndex} (${p1.x.toFixed(1)}, ${p1.y.toFixed(1)})` : 'Esperando clic...'}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>Punto Final:</span>
          <span className="font-mono" style={{ color: p2 ? 'var(--color-accent)' : 'var(--color-text-muted)' }}>
            {p2 ? `P${p2.pointIndex} (${p2.x.toFixed(1)}, ${p2.y.toFixed(1)})` : 'Esperando clic...'}
          </span>
        </div>
      </div>

      {/* Form Fields */}
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-mono font-bold mb-1 uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
            Sector
          </label>
          <input
            type="text"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            placeholder="Opcional"
            className="w-full px-3 py-2 border rounded font-mono text-sm focus:outline-none focus:border-[var(--color-accent)]"
            style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
          />
        </div>
        
        <div>
          <label className="block text-xs font-mono font-bold mb-1 uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_file.spacing')}
          </label>
          <input
            type="number"
            value={spacing}
            onChange={(e) => setSpacing(Number(e.target.value))}
            className="w-full px-3 py-2 border rounded font-mono text-sm focus:outline-none focus:border-[var(--color-accent)]"
            style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
            min={1}
            max={100}
            step={1}
          />
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <label className="block text-xs font-mono font-bold mb-1 uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
              Longitud Superior (m)
            </label>
            <input
              type="number"
              value={lengthUp}
              onChange={(e) => setLengthUp(Number(e.target.value))}
              className="w-full px-3 py-2 border rounded font-mono text-sm focus:outline-none focus:border-[var(--color-accent)]"
              style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
              min={1}
              max={1000}
              step={10}
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-mono font-bold mb-1 uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
              Longitud Inferior (m)
            </label>
            <input
              type="number"
              value={lengthDown}
              onChange={(e) => setLengthDown(Number(e.target.value))}
              className="w-full px-3 py-2 border rounded font-mono text-sm focus:outline-none focus:border-[var(--color-accent)]"
              style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
              min={1}
              max={1000}
              step={10}
            />
          </div>
        </div>

        <Button className="w-full" variant="primary" disabled={!isReady || mutation.isPending} onClick={handleGenerate}>
          {mutation.isPending ? 'Generando...' : 'Generar Perfiles'}
        </Button>

        {mutation.isError && (
          <p className="text-xs font-medium mt-2 text-center" style={{ color: 'var(--color-mine-red)' }}>
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudo generar los perfiles'}
          </p>
        )}

        {mutation.isSuccess && (
          <p className="text-xs font-medium mt-2 text-center" style={{ color: 'var(--color-mine-green)' }}>
            ¡Perfiles generados con éxito!
          </p>
        )}
      </div>
    </div>
  );
}
