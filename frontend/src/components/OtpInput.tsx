import type { ChangeEvent } from 'react';

type Props = { value: string; onChange: (value: string) => void; disabled?: boolean; id?: string };

export function OtpInput({ value, onChange, disabled = false, id = 'otp' }: Props) {
  function update(event: ChangeEvent<HTMLInputElement>) {
    onChange(event.target.value.replace(/\D/g, '').slice(0, 6));
  }
  return <input className="w-full rounded border border-gray-300 px-3 py-2 tracking-[0.3em]" id={id} inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" required value={value} disabled={disabled} onChange={update} />;
}
