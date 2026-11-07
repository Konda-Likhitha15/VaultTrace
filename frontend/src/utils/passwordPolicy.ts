export type PasswordRequirement = { label: string; met: boolean };

export function passwordRequirements(password: string): PasswordRequirement[] {
  return [
    { label: 'At least 12 characters', met: password.length >= 12 },
    { label: 'One uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'One lowercase letter', met: /[a-z]/.test(password) },
    { label: 'One number', met: /[0-9]/.test(password) },
    { label: 'One special character', met: /[^A-Za-z0-9]/.test(password) },
  ];
}

export function passwordStrength(password: string): number {
  if (!password) return 0;
  return passwordRequirements(password).filter((requirement) => requirement.met).length;
}

export function passwordPolicyMessage(password: string): string {
  const unmet = passwordRequirements(password).filter((requirement) => !requirement.met);
  return unmet.length ? `Password needs: ${unmet.map((item) => item.label.toLowerCase()).join(', ')}.` : '';
}
