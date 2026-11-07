import { useState, type DragEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, uploadDocument } from '../services/api';
import { DocumentAccessDialog } from '../components/DocumentAccessDialog';
import type { DocumentMetadata } from '../types';

type FileStatus = { file: File; status: 'queued' | 'uploading' | 'success' | 'failed'; progress: number; message?: string; document?: DocumentMetadata };
const maxUploadBytes = Number(import.meta.env.VITE_DOCUMENT_MAX_UPLOAD_BYTES || 5 * 1024 * 1024);
const allowed = new Set((import.meta.env.VITE_DOCUMENT_ALLOWED_EXTENSIONS || 'pdf,png,jpg,jpeg,txt,csv,docx,xlsx').split(',').map((item) => `.${item.trim().replace(/^\./, '').toLowerCase()}`));

export function DocumentUploadPage() {
  const { token } = useAppContext();
  const [files, setFiles] = useState<FileStatus[]>([]);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<'PRIVATE' | 'SHARED' | 'RESTRICTED'>('PRIVATE');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [shareDocument, setShareDocument] = useState<DocumentMetadata | null>(null);

  function addFiles(selected: FileList | File[]) {
    const incoming = Array.from(selected);
    setFiles((current) => {
      const known = new Set(current.map(({ file }) => `${file.name}:${file.size}:${file.lastModified}`));
      const additions = incoming.filter((file) => {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (known.has(key)) return false;
        known.add(key);
        return true;
      }).map((file) => ({ file, status: 'queued' as const, progress: 0 }));
      return [...current, ...additions];
    });
    if (!name && incoming[0]) setName(incoming[0].name.replace(/\.[^.]+$/, ''));
    setError(''); setNotice('');
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(''); setNotice('');
    if (!token || !files.some((item) => item.status === 'queued' || item.status === 'failed')) { setError('Choose at least one file that has not already uploaded.'); return; }
    const pending = files.filter((item) => item.status === 'queued' || item.status === 'failed');
    const valid = pending.filter(({ file }) => file.size >= 1 && file.size <= maxUploadBytes && allowed.has(file.name.slice(file.name.lastIndexOf('.')).toLowerCase()));
    const invalid = pending.filter((item) => !valid.includes(item));
    if (invalid.length) {
      setFiles((current) => current.map((item) => invalid.includes(item) ? { ...item, status: 'failed', message: item.file.size < 1 ? 'This file is empty.' : item.file.size > maxUploadBytes ? `File exceeds the ${Math.round(maxUploadBytes / (1024 * 1024))} MB limit.` : 'This file type is not allowed.' } : item));
      setError(`${invalid.length} file${invalid.length === 1 ? '' : 's'} need attention. Valid files will still upload.`);
    }
    if (!valid.length) return;
    setBusy(true);
    let succeeded = files.filter((item) => item.status === 'success').length;
    for (const item of valid) {
      const key = `${item.file.name}:${item.file.size}:${item.file.lastModified}`;
      setFiles((current) => current.map((entry) => `${entry.file.name}:${entry.file.size}:${entry.file.lastModified}` === key ? { ...entry, status: 'uploading', message: undefined } : entry));
      try {
        const uploaded = await uploadDocument(token, item.file, {
          document_name: files.length === 1 ? name : item.file.name.replace(/\.[^.]+$/, ''),
          category,
          description: description || undefined,
          visibility,
        }, (progress) => setFiles((current) => current.map((entry) => `${entry.file.name}:${entry.file.size}:${entry.file.lastModified}` === key ? { ...entry, progress } : entry)));
        setFiles((current) => current.map((entry) => `${entry.file.name}:${entry.file.size}:${entry.file.lastModified}` === key ? { ...entry, status: 'success', progress: 100, document: uploaded, message: 'Stored and registered.' } : entry));
        succeeded += 1;
      } catch (reason) {
        const message = await apiErrorMessage(reason, 'Upload failed.');
        setFiles((current) => current.map((entry) => `${entry.file.name}:${entry.file.size}:${entry.file.lastModified}` === key ? { ...entry, status: 'failed', message } : entry));
      }
    }
    setNotice(`${succeeded} of ${files.length} selected file${files.length === 1 ? '' : 's'} uploaded successfully.`);
    setBusy(false);
  }

  return <main className="mx-auto max-w-4xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Upload documents</h1><p className="mt-2 text-gray-600">Files are validated by the backend and stored in the configured private provider. Default visibility is private.</p></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice} <Link className="font-medium underline" to="/documents">View My Documents</Link></p>}
    <form className="mt-6 space-y-4 rounded-xl border border-gray-200 bg-white p-5" onSubmit={(event) => void submit(event)}>
      <div className="rounded-lg border-2 border-dashed border-indigo-300 bg-indigo-50/40 p-8 text-center" onDragOver={(event) => event.preventDefault()} onDrop={drop}>
        <p className="font-medium">Drag files here</p><p className="mt-1 text-sm text-gray-500">PDF, PNG, JPEG, TXT, CSV, DOCX, or XLSX · up to {Math.round(maxUploadBytes / (1024 * 1024))} MB per file</p>
        <label className="mt-4 inline-flex cursor-pointer rounded bg-indigo-700 px-4 py-2 font-medium text-white">Browse files<input className="sr-only" type="file" multiple accept={Array.from(allowed).join(',')} disabled={busy} onChange={(event) => { if (event.target.files) addFiles(event.target.files); event.target.value = ''; }} /></label>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium">Document name {files.length > 1 && <span className="font-normal text-gray-500">(used for a single file; otherwise filenames are used)</span>}<input className="mt-1 w-full rounded border px-3 py-2" maxLength={200} required={files.length <= 1} value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label className="text-sm font-medium">Category<input className="mt-1 w-full rounded border px-3 py-2" maxLength={64} required value={category} onChange={(event) => setCategory(event.target.value)} /></label>
        <label className="text-sm font-medium">Visibility<select className="mt-1 w-full rounded border px-3 py-2" value={visibility} onChange={(event) => setVisibility(event.target.value as typeof visibility)}><option value="PRIVATE">Private — owner only</option><option value="SHARED">Shared — selected users</option><option value="RESTRICTED">Restricted — explicit permissions</option></select></label>
        <label className="text-sm font-medium sm:col-span-2">Description (optional)<textarea className="mt-1 w-full rounded border px-3 py-2" maxLength={4000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      </div>
      {(visibility === 'SHARED' || visibility === 'RESTRICTED') && <p className="rounded bg-blue-50 p-3 text-sm text-blue-800">Only registered recipients you explicitly authorize can access this file. After upload, use Manage access in My Documents to add them.</p>}
      {files.length > 0 && <ul className="divide-y rounded border">{files.map((item, index) => <li className="p-3" key={`${item.file.name}-${item.file.lastModified}-${index}`}>
        <div className="flex flex-wrap justify-between gap-2"><span className="break-all font-medium">{item.file.name}</span><span className="text-sm capitalize text-gray-600">{item.status}</span></div>
        {item.status === 'uploading' && <div aria-label={`Uploading ${item.file.name}`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={item.progress} className="mt-2 h-2 rounded bg-gray-200" role="progressbar"><div className="h-full rounded bg-indigo-700" style={{ width: `${item.progress}%` }} /></div>}
        {item.message && <p className={`mt-1 text-sm ${item.status === 'failed' ? 'text-red-700' : 'text-green-700'}`}>{item.message}</p>}
        {item.document && <button className="mt-2 rounded border px-3 py-1 text-sm" onClick={() => setShareDocument(item.document ?? null)} type="button">Share this document</button>}
      </li>)}</ul>}
      <div className="flex flex-wrap gap-3"><button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={busy || !files.length || (files.length <= 1 && !name.trim()) || !category.trim()} type="submit">{busy ? 'Uploading…' : 'Upload selected files'}</button><button className="rounded border px-4 py-2" disabled={busy || !files.length} onClick={() => { setFiles([]); setError(''); }} type="button">Clear queue</button></div>
    </form>
    {token && shareDocument && <DocumentAccessDialog token={token} document={shareDocument} onClose={() => setShareDocument(null)} />}
  </main>;
}
