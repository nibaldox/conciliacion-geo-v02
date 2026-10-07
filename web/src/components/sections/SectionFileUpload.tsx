import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useFileSections } from '../../api/hooks';
import { Button } from '../ui/Button';
import { IconSections } from '../ui/Icons';
import { ProjectField, PROJECT_INPUT_CLASS } from '../ui/ProjectControls';

type AzMode = 'perpendicular' | 'local_slope';

const ACCEPTED_EXTENSIONS = ['.csv', '.txt', '.dxf'];

export function SectionFileUpload() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [spacing, setSpacing] = useState(20);
  const [lengthUp, setLengthUp] = useState(100);
  const [lengthDown, setLengthDown] = useState(100);
  const [sector, setSector] = useState('');
  const [azMode, setAzMode] = useState<AzMode>('perpendicular');
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useFileSections();

  const isValidFile = (f: File): boolean => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase();
    return ACCEPTED_EXTENSIONS.includes(ext);
  };

  const handleFileSelect = (f: File) => {
    if (isValidFile(f)) {
      setFile(f);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) handleFileSelect(selected);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    mutation.mutate({ file, spacing, length: lengthUp + lengthDown, length_up: lengthUp, length_down: lengthDown, sector, az_mode: azMode });
  };

  const clearFile = () => {
    setFile(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2" data-slot="section-file-form">
      <div onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}
        className="flex min-h-[54px] items-center gap-1 rounded-lg border border-dashed p-2 transition-colors"
        style={{ borderColor: isDragging ? 'var(--color-accent)' : file ? 'var(--status-ok-border)' : 'var(--color-border)', backgroundColor: file ? 'var(--status-ok-bg)' : 'var(--color-surface-raised)' }}>
        <input ref={inputRef} type="file" accept=".csv,.txt,.dxf" onChange={handleInputChange} className="hidden" />
        <button type="button" onClick={() => inputRef.current?.click()} className="flex min-w-0 flex-1 items-center gap-2 rounded text-left outline-none focus-visible:ring-2 focus-visible:ring-accent" aria-label={t('project_input.choose_file')}>
          <IconSections className="h-5 w-5 shrink-0 text-accent-bright" />
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-text-secondary" title={file?.name}>{file?.name ?? t('project_input.choose_file')}</span>
            <span className="block text-xs text-text-muted">{file ? `${(file.size / 1024).toFixed(1)} KB` : t('section_form_file.drop_formats')}</span>
          </span>
        </button>
        {file && <button type="button" onClick={clearFile} className="h-8 w-8 shrink-0 rounded-md text-mine-red hover:bg-surface-muted" aria-label={t('section_form_file.remove')} title={t('section_form_file.remove')}>×</button>}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <ProjectField id="file-sector" label={t('section_form_file.sector')}>
          <input id="file-sector" value={sector} onChange={(e) => setSector(e.target.value)} className={PROJECT_INPUT_CLASS} placeholder={t('project_input.optional')} />
        </ProjectField>
        <ProjectField id="file-spacing" label={t('section_form_file.spacing')}>
          <input id="file-spacing" type="number" min={1} step="any" value={spacing} onChange={(e) => setSpacing(parseFloat(e.target.value) || 20)} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="file-up" label={t('project_input.length_up')} title={t('project_input.length_help')}>
          <input id="file-up" type="number" min={1} step="any" value={lengthUp} onChange={(e) => setLengthUp(parseFloat(e.target.value) || 100)} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="file-down" label={t('project_input.length_down')} title={t('project_input.length_help')}>
          <input id="file-down" type="number" min={1} step="any" value={lengthDown} onChange={(e) => setLengthDown(parseFloat(e.target.value) || 100)} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <div className="col-span-2">
          <ProjectField id="file-azimuth" label={t('section_form_file.az_method')}>
            <select id="file-azimuth" value={azMode} onChange={(e) => setAzMode(e.target.value as AzMode)} className={PROJECT_INPUT_CLASS}>
              <option value="perpendicular">{t('section_form_file.az_perpendicular')}</option>
              <option value="local_slope">{t('section_form_file.az_local_slope')}</option>
            </select>
          </ProjectField>
        </div>
      </div>
      <Button type="submit" size="sm" fullWidth className="min-h-8" disabled={!file || mutation.isPending} loading={mutation.isPending}>
        {t(mutation.isPending ? 'section_form_file.submitting' : 'section_form_file.submit')}
      </Button>
      {mutation.isError && <p role="alert" className="text-xs text-mine-red">{t('common.error')}: {mutation.error instanceof Error ? mutation.error.message : t('section_form_file.error_generic')}</p>}
      {mutation.isSuccess && <p role="status" className="text-xs text-mine-green">{t('section_form_file.success')}</p>}
    </form>
  );
}
