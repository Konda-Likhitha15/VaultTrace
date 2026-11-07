import { useState, type FormEvent } from 'react';
import axios from 'axios';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { PasswordConfirmation } from '../components/PasswordConfirmation';
import { submitPasswordReset } from '../services/api';
import { passwordPolicyMessage } from '../utils/passwordPolicy';

export function ResetPasswordPage() {
  const location = useLocation();
  const authorizationToken = (location.state as { authorizationToken?: string } | null)?.authorizationToken;
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [complete, setComplete] = useState(false);
  if (!authorizationToken) return <Navigate to="/forgot-password" replace />;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    if (password !== confirmPassword) { setError('Passwords do not match.'); return; }
    const passwordIssue = passwordPolicyMessage(password);
    if (passwordIssue) { setError(passwordIssue); return; }
    setBusy(true);
    try { await submitPasswordReset(authorizationToken ?? '', password, confirmPassword); setComplete(true); }
    catch (cause) { setError(axios.isAxiosError(cause) && typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : 'Unable to reset password. Request a new code and try again.'); }
    finally { setBusy(false); }
  }
  return <main className="flex min-h-screen items-center justify-center px-4"><section className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm">
    <h1 className="text-3xl font-bold">Choose a new password</h1>
    {complete ? <div className="mt-5" role="status"><p className="text-green-800">Your password has been reset. Existing sessions have been invalidated.</p><Link className="mt-4 inline-block text-indigo-700 hover:underline" to="/login">Sign in</Link></div> : <form className="mt-6 space-y-4" onSubmit={submit}>
      <PasswordConfirmation password={password} confirmPassword={confirmPassword} onPassword={setPassword} onConfirmPassword={setConfirmPassword} />
      {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
      <button className="w-full rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60" type="submit" disabled={busy}>{busy ? 'Updating…' : 'Reset password'}</button>
    </form>}
  </section></main>;
}
