import { useState, type FormEvent } from 'react';
import axios from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { OtpVerification } from '../components/OtpVerification';
import { requestPasswordReset, verifyPasswordResetOtp } from '../services/api';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [sentAt, setSentAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const navigate = useNavigate();
  function message(cause: unknown) {
    return axios.isAxiosError(cause) && typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : 'Unable to complete the request. Please try again.';
  }
  async function sendCode() {
    setBusy(true); setError(''); setNotice('');
    try {
      await requestPasswordReset(email);
      setOtp(''); setSentAt(Date.now());
      setNotice('If an account matches this address, a password reset code has been sent.');
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }
  async function verifyCode() {
    setBusy(true); setError('');
    try {
      const result = await verifyPasswordResetOtp(email, otp);
      navigate('/reset-password', { state: { authorizationToken: result.authorization_token } });
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void sendCode(); }
  return <main className="flex min-h-screen items-center justify-center px-4 py-10"><section className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm">
    <h1 className="text-3xl font-bold">Reset your password</h1><p className="mt-2 text-gray-600">We’ll send a short-lived code if an account matches your email.</p>
    <form className="mt-6 space-y-4" onSubmit={submit}>
      <label className="block text-sm font-medium">Email<input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
      <button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send OTP'}</button>
    </form>
    {sentAt > 0 && <OtpVerification key={sentAt} value={otp} onChange={setOtp} onVerify={() => void verifyCode()} onResend={() => void sendCode()} busy={busy} verified={false} sentAt={sentAt} />}
    {error && <p className="mt-4 text-sm text-red-700" role="alert">{error}</p>}{notice && <p className="mt-4 text-sm text-blue-800" role="status">{notice}</p>}
    <p className="mt-5 text-sm"><Link className="text-indigo-700 hover:underline" to="/login">Return to sign in</Link></p>
  </section></main>;
}
