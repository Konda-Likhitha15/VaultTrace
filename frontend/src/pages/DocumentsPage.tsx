import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { DocumentAccessDialog } from '../components/DocumentAccessDialog';
import { DocumentPreviewDialog } from '../components/DocumentPreviewDialog';
import { useAppContext } from '../context/AppContext';
import {
  deleteDocument,
  downloadDocument,
  downloadDocumentVersion,
  getDocumentActivity,
  getDocumentVersions,
  getDocuments,
  updateDocumentMetadata,
  uploadDocumentVersion,
  apiErrorMessage,
} from '../services/api';
import type { DocumentActivity, DocumentFilters, DocumentMetadata, DocumentVersion } from '../types';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function activityDescription(event: DocumentActivity): string {
  const recipient = typeof event.details.recipient_user_id === 'number' ? `user #${event.details.recipient_user_id}` : '';
  const previous = typeof event.details.previous_permission === 'string' ? event.details.previous_permission : '';
  const next = typeof event.details.new_permission === 'string' ? event.details.new_permission : '';
  if (event.action === 'PERMISSION_GRANTED' || event.action === 'DOCUMENT_SHARED') return `Access granted to ${recipient} as ${next}.`;
  if (event.action === 'PERMISSION_UPDATED' || event.action === 'DOCUMENT_PERMISSION_CHANGED') return `${recipient}: ${previous} → ${next}.`;
  if (event.action === 'PERMISSION_REVOKED' || event.action === 'DOCUMENT_ACCESS_REVOKED') return `Access revoked for ${recipient}.`;
  if (event.action === 'DOCUMENT_ACCESS_DENIED') return 'An access request was denied.';
  return '';
}

export function DocumentsPage() {
  const { user, token } = useAppContext();
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [preview, setPreview] = useState<DocumentMetadata | null>(null);
  const [access, setAccess] = useState<DocumentMetadata | null>(null);
  const [versions, setVersions] = useState<{ document: DocumentMetadata; items: DocumentVersion[] } | null>(null);
  const [activity, setActivity] = useState<{ document: DocumentMetadata; items: DocumentActivity[] } | null>(null);
  const [filters, setFilters] = useState<DocumentFilters>({ limit: 20, offset: 0, sort_by: 'created_at', sort_order: 'desc' });

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getDocuments(token, filters)
      .then((items) => { if (active) setDocuments(items); })
      .catch(async (reason: unknown) => { if (active) setError(await apiErrorMessage(reason, 'Documents could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, reload, filters]);

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setFilters({
      search: String(values.get('search') ?? '').trim() || undefined,
      category: String(values.get('category') ?? '').trim() || undefined,
      date_from: String(values.get('date_from') ?? '') || undefined,
      date_to: String(values.get('date_to') ?? '') || undefined,
      sort_by: String(values.get('sort_by') ?? 'created_at') as DocumentFilters['sort_by'],
      sort_order: String(values.get('sort_order') ?? 'desc') as DocumentFilters['sort_order'],
      limit: 20,
      offset: 0,
    });
  }

  async function download(item: DocumentMetadata) {
    if (!token) return;
    setError(''); setActiveId(item.id);
    try {
      const blob = await downloadDocument(token, item.id);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = objectUrl; anchor.download = item.original_filename; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(objectUrl);
    } catch (reason) { setError(await apiErrorMessage(reason, 'Download failed.')); }
    finally { setActiveId(null); }
  }

  async function editMetadata(item: DocumentMetadata) {
    if (!token) return;
    const name = window.prompt('Document name', item.document_name);
    if (name === null || !name.trim()) return;
    const category = window.prompt('Category', item.category);
    if (category === null || !category.trim()) return;
    const description = window.prompt('Description (leave blank to clear)', item.description ?? '');
    if (description === null || !window.confirm(`Save metadata changes to “${item.document_name}”?`)) return;
    setActiveId(item.id); setError(''); setNotice('');
    try { await updateDocumentMetadata(token, item.id, { document_name: name, category, description: description || null }); setNotice('Document metadata updated.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Metadata update failed.')); }
    finally { setActiveId(null); }
  }

  async function uploadVersion(item: DocumentMetadata, file: File | undefined) {
    if (!token || !file) return;
    if (!window.confirm(`Upload ${file.name} as version ${item.current_version + 1} of “${item.document_name}”?`)) return;
    setActiveId(item.id); setError(''); setNotice('');
    try { await uploadDocumentVersion(token, item.id, file, () => undefined); setNotice('New document version stored.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Version upload failed.')); }
    finally { setActiveId(null); }
  }

  async function showVersions(item: DocumentMetadata) {
    if (!token) return;
    setActiveId(item.id); setError('');
    try { setVersions({ document: item, items: await getDocumentVersions(token, item.id) }); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Version history could not be loaded.')); }
    finally { setActiveId(null); }
  }

  async function showActivity(item: DocumentMetadata) {
    if (!token) return;
    setActiveId(item.id); setError('');
    try { setActivity({ document: item, items: await getDocumentActivity(token, item.id) }); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Document activity could not be loaded.')); }
    finally { setActiveId(null); }
  }

  async function remove(item: DocumentMetadata) {
    if (!token || !window.confirm(`Move “${item.document_name}” to Deleted Documents? You can restore it later.`)) return;
    setActiveId(item.id); setError(''); setNotice('');
    try { await deleteDocument(token, item.id); setNotice('Document moved to Deleted Documents.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Document could not be deleted.')); }
    finally { setActiveId(null); }
  }

  const canUpload = user?.role === 'Owner';
  return <main className="mx-auto max-w-6xl">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">My Documents</h1><p className="mt-2 text-gray-600">Documents owned by your account. Shared access appears in Shared With Me.</p></div><div className="flex gap-2"><button className="rounded border px-3 py-2 text-sm" disabled={loading} onClick={() => setReload((value) => value + 1)} type="button">Refresh</button>{canUpload && <Link className="rounded bg-indigo-700 px-3 py-2 text-sm font-medium text-white" to="/documents/upload">Upload document</Link>}</div></header>
    <form className="mt-6 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-2 lg:grid-cols-3" onSubmit={applyFilters}>
      <label className="text-sm font-medium">Name or original filename<input className="mt-1 w-full rounded border px-3 py-2" name="search" type="search" /></label>
      <label className="text-sm font-medium">Category<input className="mt-1 w-full rounded border px-3 py-2" name="category" /></label>
      <label className="text-sm font-medium">Uploaded from<input className="mt-1 w-full rounded border px-3 py-2" name="date_from" type="date" /></label>
      <label className="text-sm font-medium">Uploaded to<input className="mt-1 w-full rounded border px-3 py-2" name="date_to" type="date" /></label>
      <label className="text-sm font-medium">Sort by<select className="mt-1 w-full rounded border px-3 py-2" defaultValue="created_at" name="sort_by"><option value="created_at">Upload date</option><option value="document_name">Name</option><option value="file_size">File size</option></select></label>
      <label className="text-sm font-medium">Order<select className="mt-1 w-full rounded border px-3 py-2" defaultValue="desc" name="sort_order"><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
      <div className="flex gap-2 lg:col-span-3"><button className="rounded bg-indigo-700 px-4 py-2 text-sm font-semibold text-white" type="submit">Apply filters</button><button className="rounded border px-4 py-2 text-sm" onClick={(event) => { const form = event.currentTarget.form; form?.reset(); setFilters({ limit: 20, offset: 0, sort_by: 'created_at', sort_order: 'desc' }); }} type="button">Clear filters</button></div>
    </form>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {loading ? <p className="mt-6 text-gray-600" role="status">Loading your documents…</p> : documents.length === 0 ? <div className="mt-8 rounded-xl border border-dashed p-10 text-center">{filters.search || filters.category || filters.date_from || filters.date_to ? <><h2 className="text-lg font-semibold">No matching owned documents.</h2><p className="mt-2 text-sm text-gray-600">Try different filters or clear them to see all your documents.</p></> : <><h2 className="text-lg font-semibold">You haven't uploaded any documents yet.</h2><p className="mt-2 text-sm text-gray-600">Your owned files will appear here after an upload.</p>{canUpload && <Link className="mt-4 inline-block rounded bg-indigo-700 px-4 py-2 font-semibold text-white" to="/documents/upload">Upload Document</Link>}</>}</div> : <div className="mt-6 grid gap-4 xl:grid-cols-2">
      {documents.map((item) => <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm" key={item.id}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="break-all text-lg font-semibold">{item.document_name}</h2><p className="mt-1 text-xs text-gray-500">ID {item.id}</p></div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-800">{item.visibility}</span></div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><dt className="text-xs text-gray-500">Category</dt><dd>{item.category}</dd></div><div><dt className="text-xs text-gray-500">Type / size</dt><dd>{item.file_extension.toUpperCase()} · {formatBytes(item.file_size)}</dd></div><div><dt className="text-xs text-gray-500">Uploaded</dt><dd>{new Date(item.created_at).toLocaleString()}</dd></div><div><dt className="text-xs text-gray-500">Updated</dt><dd>{new Date(item.updated_at).toLocaleString()}</dd></div><div><dt className="text-xs text-gray-500">Current version</dt><dd>v{item.current_version}</dd></div><div><dt className="text-xs text-gray-500">Access</dt><dd>{item.visibility === 'PRIVATE' ? 'Owner only' : 'Selected users'}</dd></div></dl>
        <p className="mt-3 break-all text-sm text-gray-500">{item.original_filename}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="rounded bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={activeId !== null} onClick={() => setPreview(item)} type="button">Preview</button>
          <button className="rounded border px-3 py-2 text-sm" disabled={activeId !== null} onClick={() => void download(item)} type="button">Download</button>
          {canUpload && <button className="rounded border px-3 py-2 text-sm" disabled={activeId !== null} onClick={() => void editMetadata(item)} type="button">Edit metadata</button>}
          {canUpload && <label className="cursor-pointer rounded border px-3 py-2 text-sm">Upload version<input className="sr-only" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.docx,.xlsx" disabled={activeId !== null} onChange={(event) => { void uploadVersion(item, event.target.files?.[0]); event.target.value = ''; }} /></label>}
          <button className="rounded border px-3 py-2 text-sm" disabled={activeId !== null} onClick={() => void showVersions(item)} type="button">Version history</button>
          {canUpload && <button className="rounded border px-3 py-2 text-sm" disabled={activeId !== null} onClick={() => setAccess(item)} type="button">Manage access</button>}
          {canUpload && <button className="rounded border px-3 py-2 text-sm" disabled={activeId !== null} onClick={() => void showActivity(item)} type="button">Activity</button>}
          {canUpload && <button className="rounded border border-red-300 px-3 py-2 text-sm text-red-700" disabled={activeId !== null} onClick={() => void remove(item)} type="button">Delete</button>}
        </div>
      </article>)}
    </div>}
    {!loading && documents.length > 0 && <div className="mt-5 flex justify-between"><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={!filters.offset} onClick={() => setFilters((current) => ({ ...current, offset: Math.max(0, (current.offset ?? 0) - 20) }))} type="button">Previous</button><span className="self-center text-sm text-gray-600">Page {Math.floor((filters.offset ?? 0) / 20) + 1}</span><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={documents.length < 20} onClick={() => setFilters((current) => ({ ...current, offset: (current.offset ?? 0) + 20 }))} type="button">Next</button></div>}
    {preview && token && <DocumentPreviewDialog token={token} document={preview} onClose={() => setPreview(null)} />}
    {access && token && <DocumentAccessDialog token={token} document={access} onClose={() => { setAccess(null); setReload((value) => value + 1); }} />}
    {versions && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><section aria-modal="true" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5" role="dialog"><header className="flex justify-between"><h2 className="text-xl font-semibold">Version history · {versions.document.document_name}</h2><button className="rounded border px-3" onClick={() => setVersions(null)} type="button">Close</button></header><ul className="mt-4 divide-y rounded border">{versions.items.map((version) => <li className="flex flex-wrap justify-between gap-3 p-3" key={version.id}><div><p className="font-medium">Version {version.version_number} · {version.original_filename}</p><p className="text-xs text-gray-500">{formatBytes(version.file_size)} · uploader user #{version.created_by_user_id} · {new Date(version.created_at).toLocaleString()}</p>{version.checksum && <p className="mt-1 break-all font-mono text-xs text-gray-500">SHA-256: {version.checksum}</p>}</div>{token && <a className="rounded border px-3 py-1 text-sm" href="#download-version" onClick={async (event) => { event.preventDefault(); try { const blob = await downloadDocumentVersion(token, versions.document.id, version.id); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = version.original_filename; anchor.click(); URL.revokeObjectURL(url); } catch (reason) { setError(await apiErrorMessage(reason, 'Version download failed.')); } }}>Download</a>}</li>)}</ul></section></div>}
    {activity && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><section aria-modal="true" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5" role="dialog"><header className="flex justify-between"><h2 className="text-xl font-semibold">Activity · {activity.document.document_name}</h2><button className="rounded border px-3" onClick={() => setActivity(null)} type="button">Close</button></header>{activity.items.length ? <ul className="mt-4 divide-y">{activity.items.map((event) => <li className="py-3" key={event.id}><p className="font-medium">{event.actor_username} · {event.action.replaceAll('_', ' ').toLowerCase()}</p>{activityDescription(event) && <p className="mt-1 text-sm text-gray-700">{activityDescription(event)}</p>}<p className="text-xs text-gray-500">{new Date(event.created_at).toLocaleString()} · {event.result}</p></li>)}</ul> : <p className="mt-4 text-gray-600">No activity recorded yet.</p>}</section></div>}
  </main>;
}
