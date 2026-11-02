import { useEffect, useState } from 'react';
import { OtpInput } from './OtpInput';

type Props = { value: string; onChange: (value: string) => void; onVerify: () => void; onResend: () => void; busy: boolean; verified: boolean; sentAt: number };

export function OtpVerification({ value, onChange, onVerify, onResend, busy, verified, sentAt }: Props) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [sentAt]);
  const remaining = Math.max(0, Math.ceil((sentAt + 300_000 - now) / 1000));
  const cooldown = Math.max(0, Math.ceil((sentAt + 60_000 - now) / 1000));
  const fmt = (value: number) => `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  return <div className="sm:col-span-2">
    <label className="text-sm font-medium" htmlFor="otp">Six-digit email code</label>
    <div className="mt-1 flex gap-2">
      <OtpInput value={value} onChange={onChange} disabled={verified || remaining === 0} />
      <button className="shrink-0 rounded border border-indigo-700 px-3 py-2 font-medium text-indigo-700 disabled:opacity-60" type="button" disabled={busy || verified || value.length !== 6 || remaining === 0} onClick={onVerify}>
        {verified ? 'Verified' : busy ? 'Verifying…' : 'Verify OTP'}
      </button>
    </div>
    <p className="mt-1 text-xs text-gray-500" aria-live="polite">Code expires in {fmt(remaining)}. {cooldown > 0 ? `Resend in ${fmt(cooldown)}.` : ''}</p>
    <button className="mt-2 text-sm font-medium text-indigo-700 disabled:opacity-50" type="button" disabled={busy || cooldown > 0} onClick={onResend}>Resend OTP</button>
  </div>;
}
