import { useEffect, useState } from 'react';
import {
  getDocumentPermissions,
  grantDocumentPermission,
  revokeDocumentPermission,
  searchEligibleShareUsers,
  updateDocumentPermission,
} from '../services/api';
import { apiErrorMessage } from '../services/api';
import type { DocumentMetadata, DocumentPermission, EligibleShareUser } from '../types';

function expiryValue(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function DocumentAccessDialog({ token, document, onClose }: { token: string; document: DocumentMetadata; onClose: () => void }) {
  const [permissions, setPermissions] = useState<DocumentPermission[]>([]);
  const [query, setQuery] = useState('');
  const [recipients, setRecipients] = useState<EligibleShareUser[]>([]);
  const [recipientId, setRecipientId] = useState<number | null>(null);
  const [level, setLevel] = useState<'READ' | 'EDIT'>('READ');
  const [expiration, setExpiration] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    setLoading(true);
    try { setPermissions(await getDocumentPermissions(token, document.id)); setError(''); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Access history could not be loaded.')); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, [token, document.id]);

  async function addRecipient(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const recipient = recipients.find((item) => item.id === recipientId);
    if (!recipient || !window.confirm(`Share “${document.document_name}” with ${recipient.email} as ${level}?`)) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await grantDocumentPermission(token, document.id, { recipient_user_id: recipient.id, permission_level: level, expires_at: expiryValue(expiration) });
      setQuery(''); setRecipients([]); setRecipientId(null); setExpiration(''); setNotice('Access granted.'); await refresh();
    } catch (reason) { setError(await apiErrorMessage(reason, 'Access could not be granted.')); }
    finally { setBusy(false); }
  }

  async function findRecipients() {
    if (query.trim().length < 2) { setError('Enter at least two characters to search organization members.'); return; }
    setBusy(true); setError(''); setRecipientId(null);
    try { setRecipients(await searchEligibleShareUsers(token, document.id, query.trim())); }
    catch (reason) { setError(await apiErrorMessage(reason, 'User search failed.')); }
    finally { setBusy(false); }
  }

  async function changeLevel(permission: DocumentPermission, nextLevel: 'READ' | 'EDIT') {
    if (!window.confirm(`Change ${permission.recipient_username}'s permission to ${nextLevel}?`)) return;
    setBusy(true); setError(''); setNotice('');
    try { await updateDocumentPermission(token, document.id, permission.id, { permission_level: nextLevel }); setNotice('Permission updated.'); await refresh(); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Permission update failed.')); }
    finally { setBusy(false); }
  }

  async function revoke(permission: DocumentPermission) {
    if (!window.confirm(`Revoke ${permission.recipient_username}'s access to “${document.document_name}”?`)) return;
    setBusy(true); setError(''); setNotice('');
    try { await revokeDocumentPermission(token, document.id, permission.id); setNotice('Access revoked.'); await refresh(); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Access could not be revoked.')); }
    finally { setBusy(false); }
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
    <section aria-modal="true" aria-labelledby="document-access-title" className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl" role="dialog">
      <header className="flex items-center justify-between gap-4"><div><h2 className="text-xl font-semibold" id="document-access-title">Manage access</h2><p className="text-sm text-gray-600">{document.document_name} · ownership stays with its uploader.</p></div><button className="rounded border px-3 py-1" onClick={onClose} type="button">Close</button></header>
      {error && <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
      {notice && <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
      <form className="mt-5 grid gap-3 rounded-lg border p-4 sm:grid-cols-2" onSubmit={(event) => void addRecipient(event)}>
        <label className="text-sm font-medium sm:col-span-2">Search same-organization members by email or username
          <div className="mt-1 flex gap-2"><input className="min-w-0 flex-1 rounded border px-3 py-2" autoComplete="off" value={query} onChange={(event) => { setQuery(event.target.value); setRecipients([]); setRecipientId(null); }} /><button className="rounded border px-3 py-2 disabled:opacity-50" disabled={busy} onClick={() => void findRecipients()} type="button">{busy ? 'Searching…' : 'Search'}</button></div>
        </label>
        {recipients.length > 0 && <label className="text-sm font-medium sm:col-span-2">Registered user<select className="mt-1 w-full rounded border px-3 py-2" required value={recipientId ?? ''} onChange={(event) => setRecipientId(Number(event.target.value))}><option value="">Select a user</option>{recipients.map((item) => <option key={item.id} value={item.id}>{item.full_name} · @{item.username} · {item.email}</option>)}</select></label>}
        {query.length >= 2 && !busy && recipients.length === 0 && <p className="text-sm text-gray-600 sm:col-span-2">No active, verified users found in this document owner's organization.</p>}
        <label className="text-sm font-medium">Permission
          <select className="mt-1 w-full rounded border px-3 py-2" value={level} onChange={(event) => setLevel(event.target.value as typeof level)}><option value="READ">Read</option><option value="EDIT">Edit</option></select>
        </label>
        <label className="text-sm font-medium">Optional expiration
          <input className="mt-1 w-full rounded border px-3 py-2" type="datetime-local" value={expiration} onChange={(event) => setExpiration(event.target.value)} />
        </label>
        <button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50 sm:col-span-2 sm:justify-self-start" disabled={busy || recipientId === null} type="submit">{busy ? 'Saving…' : 'Share document'}</button>
      </form>
      <h3 className="mt-6 font-semibold">Access history</h3>
      {loading ? <p className="mt-3 text-sm text-gray-600" role="status">Loading permissions…</p> : permissions.length === 0 ? <p className="mt-3 rounded border border-dashed p-4 text-sm text-gray-600">No users have been granted access.</p> : <ul className="mt-3 divide-y rounded border">
        {permissions.map((permission) => {
          const active = !permission.revoked_at && (!permission.expires_at || Date.parse(permission.expires_at) > Date.now());
          return <li className="flex flex-wrap items-center justify-between gap-3 p-3" key={permission.id}>
            <div><p className="font-medium">{permission.recipient_name} <span className="text-sm font-normal text-gray-500">@{permission.recipient_username} · {permission.recipient_email}</span></p><p className="text-xs text-gray-500">{active ? 'Active' : permission.revoked_at ? 'Revoked' : 'Expired'} · {permission.permission_level} · shared {new Date(permission.created_at).toLocaleString()}{permission.expires_at ? ` · expires ${new Date(permission.expires_at).toLocaleString()}` : ''}</p></div>
            {active && <div className="flex items-center gap-2"><select aria-label={`Permission for ${permission.recipient_username}`} className="rounded border px-2 py-1 text-sm" value={permission.permission_level} disabled={busy} onChange={(event) => void changeLevel(permission, event.target.value as typeof level)}><option value="READ">Read</option><option value="EDIT">Edit</option></select><button className="rounded border border-red-300 px-2 py-1 text-sm text-red-700" disabled={busy} onClick={() => void revoke(permission)} type="button">Revoke</button></div>}
          </li>;
        })}
      </ul>}
      <button className="mt-4 rounded border px-3 py-2 text-sm" disabled={loading || busy} onClick={() => void refresh()} type="button">Refresh access</button>
    </section>
  </div>;
}
