import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { DocumentPreviewDialog } from '../components/DocumentPreviewDialog';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, downloadDocument, getSharedWithMe, updateDocumentMetadata, uploadDocumentVersion } from '../services/api';
import type { DocumentMetadata, SharedDocument } from '../types';

export function SharedWithMePage() {
  const { token } = useAppContext();
  const [documents, setDocuments] = useState<SharedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);
  const [preview, setPreview] = useState<DocumentMetadata | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getSharedWithMe(token).then((items) => { if (active) setDocuments(items); }).catch(async (reason: unknown) => {
      if (active) setError(await apiErrorMessage(reason, 'Shared documents could not be loaded.'));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, reload]);

  async function download(item: SharedDocument) {
    if (!token) return;
    setBusyDocumentId(item.document.id); setError(''); setNotice('');
    try { const blob = await downloadDocument(token, item.document.id); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = item.document.original_filename; anchor.click(); URL.revokeObjectURL(url); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Download failed.')); }
    finally { setBusyDocumentId(null); }
  }

  async function edit(item: SharedDocument) {
    if (!token) return;
    const name = window.prompt('Document name', item.document.document_name);
    if (name === null || !name.trim() || !window.confirm(`Save this change to “${item.document.document_name}”?`)) return;
    setBusyDocumentId(item.document.id); setError(''); setNotice('');
    try { await updateDocumentMetadata(token, item.document.id, { document_name: name }); setNotice('Document name updated.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Metadata update failed.')); }
    finally { setBusyDocumentId(null); }
  }

  async function newVersion(item: SharedDocument, file?: File) {
    if (!token || !file || !window.confirm(`Upload ${file.name} as a new version of “${item.document.document_name}”?`)) return;
    setBusyDocumentId(item.document.id); setError(''); setNotice('');
    try { await uploadDocumentVersion(token, item.document.id, file, () => undefined); setNotice('New version uploaded.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'New version upload failed.')); }
    finally { setBusyDocumentId(null); }
  }

  return <main className="mx-auto max-w-6xl">
    <header className="flex items-end justify-between gap-3"><div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Shared With Me</h1><p className="mt-2 text-gray-600">Only explicit, active grants are listed. Expired or revoked access is excluded.</p></div><button className="rounded border px-3 py-2 text-sm" onClick={() => setReload((value) => value + 1)} type="button">Refresh</button></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {loading ? <p className="mt-6" role="status">Loading shared documents…</p> : documents.length === 0 ? <div className="mt-8 rounded-xl border border-dashed p-10 text-center"><h2 className="font-semibold">No documents have been shared with you.</h2><p className="mt-2 text-sm text-gray-600">When an owner grants access, the document will appear here.</p><Link className="mt-4 inline-block text-indigo-700 underline" to="/documents/search">Search your authorized documents</Link></div> : <div className="mt-6 grid gap-4 md:grid-cols-2">{documents.map((item) => {
      const canEdit = item.permission_level === 'EDIT';
      const doc = item.document;
      return <article className="rounded-xl border bg-white p-5" key={`${doc.id}-${item.shared_at}`}>
        <div className="flex items-start justify-between gap-3"><h2 className="font-semibold">{doc.document_name}</h2><span className="rounded bg-indigo-50 px-2 py-1 text-xs text-indigo-800">{item.permission_level}</span></div>
        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm"><div><dt className="text-xs text-gray-500">Owner</dt><dd>{item.owner_name} (@{item.owner_username})</dd></div><div><dt className="text-xs text-gray-500">Category</dt><dd>{doc.category}</dd></div><div><dt className="text-xs text-gray-500">Shared</dt><dd>{new Date(item.shared_at).toLocaleString()}</dd></div><div><dt className="text-xs text-gray-500">Expires</dt><dd>{item.expires_at ? new Date(item.expires_at).toLocaleString() : 'No expiry set'}</dd></div><div><dt className="text-xs text-gray-500">Access</dt><dd>Active</dd></div></dl>
        <div className="mt-4 flex flex-wrap gap-2"><button className="rounded bg-indigo-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={busyDocumentId !== null} onClick={() => setPreview(doc)} type="button">Preview</button><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={busyDocumentId !== null} onClick={() => void download(item)} type="button">{busyDocumentId === doc.id ? 'Working…' : 'Download'}</button>{canEdit && <button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={busyDocumentId !== null} onClick={() => void edit(item)} type="button">Edit name</button>}{canEdit && <label className={`rounded border px-3 py-2 text-sm ${busyDocumentId !== null ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>Upload version<input className="sr-only" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.docx,.xlsx" disabled={busyDocumentId !== null} onChange={(event) => { void newVersion(item, event.target.files?.[0]); event.target.value = ''; }} /></label>}</div>
      </article>;
    })}</div>}
    {preview && token && <DocumentPreviewDialog token={token} document={preview} onClose={() => setPreview(null)} />}
  </main>;
}
