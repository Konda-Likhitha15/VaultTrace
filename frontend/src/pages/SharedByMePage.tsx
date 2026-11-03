import { useEffect, useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, getSharedByMe, revokeDocumentPermission, updateDocumentPermission } from '../services/api';
import type { SharedByMe } from '../types';

export function SharedByMePage() {
  const { token } = useAppContext();
  const [items, setItems] = useState<SharedByMe[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getSharedByMe(token).then((result) => { if (active) setItems(result); }).catch(async (reason: unknown) => {
      if (active) setError(await apiErrorMessage(reason, 'Shared access could not be loaded.'));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, reload]);

  async function update(item: SharedByMe, level: 'READ' | 'EDIT') {
    if (!token || !window.confirm(`Change ${item.recipient_username}'s access to ${level}?`)) return;
    setBusy(item.permission_id); setError(''); setNotice('');
    try { await updateDocumentPermission(token, item.document_id, item.permission_id, { permission_level: level }); setNotice('Permission updated.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Permission update failed.')); }
    finally { setBusy(null); }
  }

  async function revoke(item: SharedByMe) {
    if (!token || !window.confirm(`Revoke ${item.recipient_username}'s access to “${item.document_name}”?`)) return;
    setBusy(item.permission_id); setError(''); setNotice('');
    try { await revokeDocumentPermission(token, item.document_id, item.permission_id); setNotice('Access revoked.'); setReload((value) => value + 1); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Access could not be revoked.')); }
    finally { setBusy(null); }
  }

  return <main className="mx-auto max-w-6xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Shared By Me</h1><p className="mt-2 text-gray-600">Review recipients, permission levels, expiration, and current access state.</p></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {loading ? <p className="mt-6" role="status">Loading your access grants…</p> : items.length === 0 ? <div className="mt-8 rounded-xl border border-dashed p-10 text-center"><p className="font-semibold">You haven't shared any documents.</p><p className="mt-2 text-sm text-gray-600">Grant access from Manage Access on one of your documents.</p></div> : <div className="mt-6 overflow-x-auto rounded-xl border bg-white"><table className="min-w-[760px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="px-4 py-3">Document</th><th className="px-4 py-3">Recipient</th><th className="px-4 py-3">Permission</th><th className="px-4 py-3">Shared / expires</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Actions</th></tr></thead><tbody className="divide-y">{items.map((item) => {
      const active = !item.revoked_at && (!item.expires_at || Date.parse(item.expires_at) > Date.now());
      return <tr key={item.permission_id}><td className="px-4 py-3"><span className="font-medium">{item.document_name}</span><span className="block text-xs text-gray-500">{item.document_id}</span></td><td className="px-4 py-3">{item.recipient_name}<span className="block text-xs text-gray-500">@{item.recipient_username} · ID {item.recipient_user_id}</span></td><td className="px-4 py-3">{active ? <select aria-label={`Permission for ${item.recipient_username}`} className="rounded border px-2 py-1" disabled={busy !== null} value={item.permission_level} onChange={(event) => void update(item, event.target.value as 'READ' | 'EDIT')}><option value="READ">Read</option><option value="EDIT">Edit</option></select> : item.permission_level}</td><td className="px-4 py-3">{new Date(item.shared_at).toLocaleDateString()}<span className="block text-xs text-gray-500">{item.expires_at ? `Expires ${new Date(item.expires_at).toLocaleString()}` : 'No expiry'}</span></td><td className="px-4 py-3">{item.revoked_at ? 'Revoked' : active ? 'Active' : 'Expired'}</td><td className="px-4 py-3">{active && <button className="rounded border border-red-300 px-2 py-1 text-red-700" disabled={busy !== null} onClick={() => void revoke(item)} type="button">{busy === item.permission_id ? 'Saving…' : 'Revoke'}</button>}</td></tr>;
    })}</tbody></table></div>}
  </main>;
}
