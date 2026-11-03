import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';
import { getAdminDocumentAudit, getAdminDocumentPermissions, getAdminDocuments, revokeAdminDocumentPermission } from '../services/api';
import type { DocumentActivity } from '../types';

type AdminDocument = Awaited<ReturnType<typeof getAdminDocuments>>[number];

function messageFor(reason: unknown, fallback: string): string {
  return axios.isAxiosError(reason) && typeof reason.response?.data?.detail === 'string' ? reason.response.data.detail : fallback;
}

export function AdminDocumentsPage() {
  const { token } = useAppContext();
  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [events, setEvents] = useState<DocumentActivity[]>([]);
  const [permissions, setPermissions] = useState<Awaited<ReturnType<typeof getAdminDocumentPermissions>>>([]);
  const [search, setSearch] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void Promise.all([getAdminDocuments(token, search.trim() || undefined), getAdminDocumentAudit(token, documentId.trim() || undefined), getAdminDocumentPermissions(token, documentId.trim() || undefined)])
      .then(([rows, audit, grants]) => { if (active) { setDocuments(rows); setEvents(audit); setPermissions(grants); } })
      .catch((reason: unknown) => { if (active) setError(messageFor(reason, 'Administrative document metadata could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, search, documentId, reload]);

  async function revokePermission(permissionId: number) {
    if (!token || !window.confirm('Revoke this document access grant? This does not expose or modify file contents.')) return;
    setError('');
    try { await revokeAdminDocumentPermission(token, permissionId); setReload((value) => value + 1); }
    catch (reason) { setError(messageFor(reason, 'Permission could not be revoked.')); }
  }

  return <main className="mx-auto max-w-7xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Administration</p><h1 className="mt-1 text-3xl font-bold">Document metadata & audit</h1><p className="mt-2 text-gray-600">Administrative access is limited to metadata and access events. File contents are not available here.</p></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    <section className="mt-7 rounded-xl border bg-white p-4">
      <h2 className="text-xl font-semibold">All document metadata</h2>
      <label className="mt-4 block text-sm font-medium">Search document or owner<input className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setSearch(event.target.value)} placeholder="Name, filename, owner" value={search} /></label>
      {loading ? <p className="mt-4" role="status">Loading administrative records…</p> : documents.length === 0 ? <p className="mt-4 text-gray-600">No matching document metadata.</p> : <div className="mt-4 overflow-x-auto"><table className="min-w-[900px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="p-3">Document</th><th className="p-3">Owner</th><th className="p-3">Category / type</th><th className="p-3">Visibility</th><th className="p-3">State</th><th className="p-3">Uploaded</th></tr></thead><tbody className="divide-y">{documents.map((item) => <tr key={item.id}><td className="p-3"><span className="font-medium">{item.document_name}</span><span className="block break-all text-xs text-gray-500">{item.id} · {item.original_filename}</span></td><td className="p-3">{item.owner_name}<span className="block text-xs text-gray-500">@{item.owner_username} · #{item.owner_id}</span></td><td className="p-3">{item.category} · {item.file_extension}</td><td className="p-3">{item.visibility}</td><td className="p-3">{item.deleted_at ? 'Deleted' : `Version ${item.current_version}`}</td><td className="p-3">{new Date(item.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>}
    </section>
    <section className="mt-7 rounded-xl border bg-white p-4">
      <h2 className="text-xl font-semibold">Access permissions</h2>
      {permissions.length === 0 && !loading ? <p className="mt-4 text-gray-600">No permission records for this filter.</p> : <div className="mt-4 overflow-x-auto"><table className="min-w-[760px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="p-3">Document</th><th className="p-3">Owner ID</th><th className="p-3">Recipient</th><th className="p-3">Permission</th><th className="p-3">Expires</th><th className="p-3">Status</th><th className="p-3">Action</th></tr></thead><tbody className="divide-y">{permissions.map((grant) => { const active = !grant.revoked_at && (!grant.expires_at || Date.parse(grant.expires_at) > Date.now()); return <tr key={grant.id}><td className="p-3">{grant.document_name}<span className="block break-all text-xs text-gray-500">{grant.document_id}</span></td><td className="p-3">#{grant.owner_id}</td><td className="p-3">{grant.recipient_username} (#{grant.recipient_user_id})</td><td className="p-3">{grant.permission_level}</td><td className="p-3">{grant.expires_at ? new Date(grant.expires_at).toLocaleString() : 'No expiry'}</td><td className="p-3">{grant.revoked_at ? 'Revoked' : active ? 'Active' : 'Expired'}</td><td className="p-3">{active && <button className="rounded border border-red-300 px-2 py-1 text-red-700" onClick={() => void revokePermission(grant.id)} type="button">Revoke</button>}</td></tr>; })}</tbody></table></div>}
    </section>
    <section className="mt-7 rounded-xl border bg-white p-4">
      <h2 className="text-xl font-semibold">Document access audit</h2>
      <label className="mt-4 block text-sm font-medium">Filter by document UUID<input className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setDocumentId(event.target.value)} placeholder="Optional document UUID" value={documentId} /></label>
      {events.length === 0 && !loading ? <p className="mt-4 text-gray-600">No audit events for this filter.</p> : <div className="mt-4 overflow-x-auto"><table className="min-w-[760px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="p-3">Time</th><th className="p-3">Actor</th><th className="p-3">Action</th><th className="p-3">Result</th><th className="p-3">Document</th><th className="p-3">Administrative action</th></tr></thead><tbody className="divide-y">{events.map((event) => { const permissionId = typeof event.details.permission_id === 'number' ? event.details.permission_id : null; return <tr key={event.id}><td className="p-3">{new Date(event.created_at).toLocaleString()}</td><td className="p-3">{event.actor_username} (#{event.actor_user_id})</td><td className="p-3">{event.action}</td><td className="p-3">{event.result}</td><td className="p-3 break-all">{event.document_id ?? '—'}</td><td className="p-3">{permissionId !== null && event.action === 'DOCUMENT_SHARED' && <button className="rounded border border-red-300 px-2 py-1 text-red-700" onClick={() => void revokePermission(permissionId)} type="button">Revoke grant</button>}</td></tr>; })}</tbody></table></div>}
    </section>
  </main>;
}
