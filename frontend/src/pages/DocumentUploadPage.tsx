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
    setFiles((current) => [...current, ...incoming.filter((file) => !current.some((item) => item.file.name === file.name && item.file.size === file.size)).map((file) => ({ file, status: 'queued' as const, progress: 0 }))]);
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
    if (!token || !files.length) { setError('Choose at least one file to upload.'); return; }
    const invalid = files.find(({ file }) => file.size < 1 || file.size > maxUploadBytes || !allowed.has(file.name.slice(file.name.lastIndexOf('.')).toLowerCase()));
    if (invalid) { setError(`${invalid.file.name} is empty, too large, or has a disallowed extension.`); return; }
    setBusy(true);
    let succeeded = 0;
    for (let index = 0; index < files.length; index += 1) {
      const item = files[index];
      setFiles((current) => current.map((entry, currentIndex) => currentIndex === index ? { ...entry, status: 'uploading' } : entry));
      try {
        const uploaded = await uploadDocument(token, item.file, {
          document_name: files.length === 1 ? name : item.file.name.replace(/\.[^.]+$/, ''),
          category,
          description: description || undefined,
          visibility,
        }, (progress) => setFiles((current) => current.map((entry, currentIndex) => currentIndex === index ? { ...entry, progress } : entry)));
        setFiles((current) => current.map((entry, currentIndex) => currentIndex === index ? { ...entry, status: 'success', progress: 100, document: uploaded, message: 'Stored and registered.' } : entry));
        succeeded += 1;
      } catch (reason) {
        const message = await apiErrorMessage(reason, 'Upload failed.');
        setFiles((current) => current.map((entry, currentIndex) => currentIndex === index ? { ...entry, status: 'failed', message } : entry));
      }
    }
    setNotice(`${succeeded} of ${files.length} file${files.length === 1 ? '' : 's'} uploaded successfully.`);
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
        <label className="text-sm font-medium">Document name {files.length > 1 && <span className="font-normal text-gray-500">(applies when one file is selected)</span>}<input className="mt-1 w-full rounded border px-3 py-2" maxLength={200} required value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label className="text-sm font-medium">Category<input className="mt-1 w-full rounded border px-3 py-2" maxLength={64} required value={category} onChange={(event) => setCategory(event.target.value)} /></label>
        <label className="text-sm font-medium">Visibility<select className="mt-1 w-full rounded border px-3 py-2" value={visibility} onChange={(event) => setVisibility(event.target.value as typeof visibility)}><option value="PRIVATE">Private — owner only</option><option value="SHARED">Shared — selected users</option><option value="RESTRICTED">Restricted — explicit permissions</option></select></label>
        <label className="text-sm font-medium sm:col-span-2">Description (optional)<textarea className="mt-1 w-full rounded border px-3 py-2" maxLength={4000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      </div>
      {(visibility === 'SHARED' || visibility === 'RESTRICTED') && <p className="rounded bg-blue-50 p-3 text-sm text-blue-800">Only registered recipients you explicitly authorize can access this file. After upload, use Manage access in My Documents to add them.</p>}
      {files.length > 0 && <ul className="divide-y rounded border">{files.map((item, index) => <li className="p-3" key={`${item.file.name}-${item.file.lastModified}-${index}`}>
        <div className="flex flex-wrap justify-between gap-2"><span className="break-all font-medium">{item.file.name}</span><span className="text-sm capitalize text-gray-600">{item.status}</span></div>
        {item.status === 'uploading' && <div className="mt-2 h-2 rounded bg-gray-200"><div className="h-full rounded bg-indigo-700" style={{ width: `${item.progress}%` }} /></div>}
        {item.message && <p className={`mt-1 text-sm ${item.status === 'failed' ? 'text-red-700' : 'text-green-700'}`}>{item.message}</p>}
        {item.document && <button className="mt-2 rounded border px-3 py-1 text-sm" onClick={() => setShareDocument(item.document ?? null)} type="button">Share this document</button>}
      </li>)}</ul>}
      <div className="flex flex-wrap gap-3"><button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={busy || !files.length || !name.trim() || !category.trim()} type="submit">{busy ? 'Uploading…' : 'Upload selected files'}</button><button className="rounded border px-4 py-2" disabled={busy || !files.length} onClick={() => { setFiles([]); setError(''); }} type="button">Clear queue</button></div>
    </form>
    {token && shareDocument && <DocumentAccessDialog token={token} document={shareDocument} onClose={() => setShareDocument(null)} />}
  </main>;
}
