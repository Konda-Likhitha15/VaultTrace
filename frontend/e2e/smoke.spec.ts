import { expect, test } from '@playwright/test';

test('shows the common sign-in page by default', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
});

test('signup requires email verification before submission', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByRole('heading', { name: 'Apply for an account' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send OTP' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit signup application' })).toBeDisabled();
});
