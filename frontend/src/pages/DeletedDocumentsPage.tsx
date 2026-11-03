import { useEffect, useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, getDeletedDocuments, restoreDocument } from '../services/api';
import type { DocumentMetadata } from '../types';

export function DeletedDocumentsPage() {
  const { token } = useAppContext();
  const [items, setItems] = useState<DocumentMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getDeletedDocuments(token).then((result) => { if (active) setItems(result); }).catch(async (reason: unknown) => {
      if (active) setError(await apiErrorMessage(reason, 'Deleted documents could not be loaded.'));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, reload]);

  async function restore(item: DocumentMetadata) {
    if (!token || !window.confirm(`Restore “${item.document_name}”? Previous shares remain revoked.`)) return;
    setBusy(item.id); setError(''); setNotice('');
    try { await restoreDocument(token, item.id); setNotice('Document restored.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Document could not be restored.')); }
    finally { setBusy(null); }
  }

  return <main className="mx-auto max-w-5xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Deleted Documents</h1><p className="mt-2 text-gray-600">Deleted documents remain private and recoverable. Restoring one does not restore old access grants.</p></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {loading ? <p className="mt-6" role="status">Loading deleted documents…</p> : items.length === 0 ? <div className="mt-8 rounded-xl border border-dashed p-10 text-center">No deleted documents.</div> : <ul className="mt-6 divide-y rounded-xl border bg-white">{items.map((item) => <li className="flex flex-wrap items-center justify-between gap-3 p-4" key={item.id}><div><p className="font-medium">{item.document_name}</p><p className="mt-1 text-sm text-gray-600">{item.original_filename} · deleted {item.deleted_at ? new Date(item.deleted_at).toLocaleString() : 'date unavailable'}</p></div><button className="rounded bg-indigo-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={busy !== null} onClick={() => void restore(item)} type="button">{busy === item.id ? 'Restoring…' : 'Restore'}</button></li>)}</ul>}
  </main>;
}
