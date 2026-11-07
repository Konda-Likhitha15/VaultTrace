import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { PasswordField } from '../components/PasswordField';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, changeMyPassword, updateMyProfile } from '../services/api';
import { passwordPolicyMessage } from '../utils/passwordPolicy';

export function ProfilePage() {
  const { user, token, refreshUser, logout } = useAppContext();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [phone, setPhone] = useState(user?.phone_number ?? '');
  const [profileError, setProfileError] = useState('');
  const [profileNotice, setProfileNotice] = useState('');
  const [profileBusy, setProfileBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordNotice, setPasswordNotice] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);

  useEffect(() => { void refreshUser().catch(() => setProfileError('Your profile could not be refreshed. Sign in again.')); }, [refreshUser]);
  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name); setUsername(user.username); setPhone(user.phone_number ?? '');
  }, [user]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return;
    setProfileBusy(true); setProfileError(''); setProfileNotice('');
    try {
      await updateMyProfile(token, { full_name: fullName.trim(), username: username.trim(), phone_number: phone.trim() || null });
      await refreshUser(); setProfileNotice('Profile changes saved.'); setEditing(false);
    } catch (reason) { setProfileError(await apiErrorMessage(reason, 'Profile changes could not be saved.')); }
    finally { setProfileBusy(false); }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return;
    setPasswordError(''); setPasswordNotice('');
    const policy = passwordPolicyMessage(newPassword);
    if (policy) { setPasswordError(policy); return; }
    if (newPassword !== confirmPassword) { setPasswordError('New password and confirmation do not match.'); return; }
    setPasswordBusy(true);
    try {
      await changeMyPassword(token, { current_password: currentPassword, password: newPassword, confirm_password: confirmPassword });
      setPasswordNotice('Password updated. Signing you out so you can sign in with your new password.');
      await logout(); navigate('/login', { replace: true, state: { notice: 'Password updated. Sign in with your new password.' } });
    } catch (reason) { setPasswordError(await apiErrorMessage(reason, 'Password could not be changed.')); }
    finally { setPasswordBusy(false); }
  }

  if (!user) return <p role="status">Loading profile…</p>;
  return <main className="mx-auto grid w-full max-w-5xl gap-6 xl:grid-cols-2">
    <header className="xl:col-span-2"><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Account</p><h1 className="mt-1 text-3xl font-bold">Profile</h1><p className="mt-2 text-gray-600">Manage your personal information and account security.</p></header>
    <section className="rounded-xl border bg-white p-6 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Personal information</h2><p className="mt-1 text-sm text-gray-500">Email, role, account status, and organization are read-only.</p></div>{!editing && <button className="rounded border px-3 py-2 text-sm font-medium" onClick={() => { setProfileError(''); setProfileNotice(''); setEditing(true); }} type="button">Edit profile</button>}</div>
      {editing ? <form className="mt-5 space-y-4" onSubmit={saveProfile}>
        <div><label className="block text-sm font-medium" htmlFor="profile-name">Full name</label><input autoComplete="name" className="mt-1 w-full rounded border px-3 py-2" id="profile-name" maxLength={160} required value={fullName} onChange={(event) => setFullName(event.target.value)} /></div>
        <div><label className="block text-sm font-medium" htmlFor="profile-username">Username</label><input autoComplete="username" className="mt-1 w-full rounded border px-3 py-2" id="profile-username" maxLength={32} minLength={3} pattern="[A-Za-z0-9_.-]+" required value={username} onChange={(event) => setUsername(event.target.value)} /><p className="mt-1 text-xs text-gray-500">3–32 letters, numbers, dots, underscores, or hyphens.</p></div>
        <div><label className="block text-sm font-medium" htmlFor="profile-phone">Phone number</label><input autoComplete="tel" className="mt-1 w-full rounded border px-3 py-2" id="profile-phone" maxLength={32} value={phone} onChange={(event) => setPhone(event.target.value)} /></div>
        <div className="flex gap-2"><button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={profileBusy} type="submit">{profileBusy ? 'Saving…' : 'Save changes'}</button><button className="rounded border px-4 py-2 font-medium" disabled={profileBusy} onClick={() => { setFullName(user.full_name); setUsername(user.username); setPhone(user.phone_number ?? ''); setEditing(false); }} type="button">Cancel</button></div>
      </form> : <dl className="mt-5 grid gap-4 rounded-lg bg-gray-50 p-4 text-sm sm:grid-cols-2"><div><dt className="text-gray-500">Full name</dt><dd className="font-medium">{user.full_name}</dd></div><div><dt className="text-gray-500">Username</dt><dd className="font-medium">@{user.username}</dd></div><div><dt className="text-gray-500">Phone</dt><dd>{user.phone_number || 'Not provided'}</dd></div><div><dt className="text-gray-500">Email</dt><dd className="break-all">{user.email}</dd></div><div><dt className="text-gray-500">Role and status</dt><dd>{user.role} · {user.account_status}</dd></div><div><dt className="text-gray-500">Organization</dt><dd>{user.organization_name ?? 'Not assigned'}</dd></div><div><dt className="text-gray-500">Account created</dt><dd>{user.created_at ? new Date(user.created_at).toLocaleDateString() : 'Not available'}</dd></div></dl>}
      {profileError && <p className="mt-4 text-sm text-red-700" role="alert">{profileError}</p>}{profileNotice && <p className="mt-4 text-sm text-green-800" role="status">{profileNotice}</p>}
    </section>
    <section className="rounded-xl border bg-white p-6 shadow-sm"><h2 className="text-xl font-semibold">Security settings</h2><p className="mt-1 text-sm text-gray-500">Your current password is required. Changing it signs out existing sessions.</p>
      <form className="mt-5 space-y-4" onSubmit={savePassword}>
        <PasswordField id="current-password" label="Current password" autoComplete="current-password" value={currentPassword} onChange={setCurrentPassword} />
        <PasswordField id="new-password" label="New password" autoComplete="new-password" minLength={12} value={newPassword} onChange={setNewPassword} showStrength />
        <PasswordField id="confirm-new-password" label="Confirm new password" autoComplete="new-password" minLength={12} value={confirmPassword} onChange={setConfirmPassword} />
        {passwordError && <p className="text-sm text-red-700" role="alert">{passwordError}</p>}{passwordNotice && <p className="text-sm text-green-800" role="status">{passwordNotice}</p>}
        <button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={passwordBusy} type="submit">{passwordBusy ? 'Updating…' : 'Change password'}</button>
      </form>
    </section>
  </main>;
}
