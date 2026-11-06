import axios from 'axios';

export interface BlastImportPreview {
  file_type: 'csv' | 'xlsx';
  encoding: string | null;
  sheets: string[];
  sheet_name: string | null;
  headers: string[];
  preview: Record<string, unknown>[];
  suggested_mapping: Record<string, string | null>;
  confidence: Record<string, unknown>;
  missing_required: string[];
}

const previewClient = axios.create({ baseURL: import.meta.env.VITE_API_URL?.trim() || '/api/v1', timeout: 120000 });

export async function previewBlastImport(file: File, sheetName?: string): Promise<BlastImportPreview> {
  const form = new FormData();
  form.append('file', file);
  if (sheetName) form.append('sheet_name', sheetName);
  const { data } = await previewClient.post<BlastImportPreview>('/blast/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
