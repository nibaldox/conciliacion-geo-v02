import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUploadBlastCsv, useBlastHolesBySession } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import type { BlastUploadResponse } from '../../api/types';

export interface BlastUploaderProps {
  onUploaded?: (response: BlastUploadResponse) => void;
}

export function BlastUploader({ onUploaded }: BlastUploaderProps) {
  const { t } = useTranslation();
  const sessionId = getSessionId();
  const upload = useUploadBlastCsv();
  const holes = useBlastHolesBySession(sessionId ?? null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [filename, setFilename] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setFilename(file.name);
    try {
      const result = await upload.mutateAsync({ sessionId, file });
      onUploaded?.(result);
    } catch {
      // Error state is surfaced via upload.isError.
    }
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border p-4"
      style={{
        borderColor: 'var(--color-border)',
        backgroundColor: 'var(--color-surface-muted)',
      }}
      data-testid="blast-uploader"
    >
      <h3
        className="text-sm font-semibold"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('blast.upload_title')}
      </h3>
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        data-testid="blast-file-input"
        onChange={handleFileChange}
        disabled={!sessionId || upload.isPending}
        className="text-xs file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1.5 file:text-white file:transition-colors disabled:opacity-50"
        style={{ color: 'var(--color-text-primary)' }}
      />
      {!sessionId && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.upload_no_session', { defaultValue: 'Inicie una sesión para cargar pozos.' })}
        </p>
      )}
      {filename && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.file_selected', { filename })}
        </p>
      )}
      {upload.isPending && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.uploading')}
        </p>
      )}
      {upload.isError && (
        <p className="text-xs" role="alert" style={{ color: 'var(--color-status-error, #ef4444)' }}>
          {t('blast.upload_error', { error: String(upload.error) })}
        </p>
      )}
      {upload.isSuccess && upload.data && (
        <div data-testid="blast-upload-summary">
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {t('blast.upload_summary', { n: upload.data.n_holes, skipped: upload.data.n_rows_skipped })}
          </p>
          {upload.data.carga_mean != null && (
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {t('blast.carga_mean', { value: upload.data.carga_mean.toFixed(2) })}
            </p>
          )}
          {upload.data.descarga_mean != null && (
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {t('blast.descarga_mean', { value: upload.data.descarga_mean.toFixed(2) })}
            </p>
          )}
        </div>
      )}
      {holes.data && (
        <p className="text-xs" data-testid="blast-hole-count" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.persisted_count', { n: holes.data.holes.length })}
        </p>
      )}
    </section>
  );
}
