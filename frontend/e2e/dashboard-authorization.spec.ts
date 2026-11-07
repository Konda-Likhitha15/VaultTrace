import { expect, test, type Page } from '@playwright/test';

const dashboardCounts = {
  total_registered_users: 3,
  total_active_users: 2,
  total_pending_applications: 1,
  total_approved_users: 2,
  total_rejected_applications: 0,
  total_owners: 1,
  total_viewers: 1,
  total_documents: 4,
  active_document_shares: 2,
};
const adminAnalytics = {
  period: '30d', total_registered_users: 3, total_active_users: 2, total_inactive_users: 1,
  pending_applications: 1, total_documents: 4, total_storage_bytes: 2048,
  total_shared_documents: 2, storage_quota_bytes: null,
  registration_trends: [], upload_trends: [], user_status: [], file_types: [],
  storage_by_organization: [], storage_by_user: [], sharing_activity: [],
  storage_growth_available: false, storage_growth_note: 'Historical snapshots unavailable.',
};

async function mockLogin(page: Page, role: 'Administrator' | 'Owner' | 'Viewer') {
  const user = {
    id: 10,
    email: `${role.toLowerCase()}@example.test`,
    full_name: 'Test User',
    username: `test-${role.toLowerCase()}`,
    role,
    account_status: 'ACTIVE',
  };
  let currentUser = user;
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname.endsWith('/auth/login')) {
      await route.fulfill({ json: { access_token: 'mock-access-token', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user } });
    } else if (url.pathname.endsWith('/users/me')) {
      if (method === 'PATCH') {
        currentUser = { ...currentUser, ...route.request().postDataJSON() };
        await route.fulfill({ json: currentUser });
      } else await route.fulfill({ json: currentUser });
    } else if (url.pathname.endsWith('/users/me/password')) {
      await route.fulfill({ status: 204 });
    } else if (url.pathname.endsWith('/users/me/storage-usage')) {
      await route.fulfill({ json: { total_stored_bytes: 0, quota_bytes: null } });
    } else if (url.pathname.endsWith('/admin/dashboard')) {
      await route.fulfill({ json: dashboardCounts });
    } else if (url.pathname.endsWith('/admin/analytics')) {
      await route.fulfill({ json: adminAnalytics });
    } else if (url.pathname.endsWith('/admin/audit-logs/summary')) {
      await route.fulfill({ json: { total_events: 0, successful_operations: 0, failed_operations: 0, active_users: 0 } });
    } else if (url.pathname.endsWith('/admin/audit-logs')) {
      await route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0 } });
    } else if (url.pathname.endsWith('/documents/')) {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ json: [] });
    }
  });
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill('test-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test('administrator sees administrator navigation', async ({ page }) => {
  await mockLogin(page, 'Administrator');
  const navigation = page.getByRole('navigation', { name: 'Admin navigation' });
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'All users' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Applications' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Documents & audit' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Audit Trail' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Audit Trail' }).click();
  await expect(page).toHaveURL(/\/admin\/audit-trail$/);
  await expect(page.getByRole('heading', { name: 'Audit Trail' })).toBeVisible();
  await expect(page.getByText('No audit events match these filters.')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'User navigation' })).toHaveCount(0);
});

test('owner sees document controls and cannot open admin routes directly', async ({ page }) => {
  await mockLogin(page, 'Owner');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await expect(page).toHaveURL(/\/owner\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'My documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Upload documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Search documents' })).toBeVisible();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/audit-trail');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/owner\/dashboard$/);
  await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: 'User navigation' }).getByRole('link', { name: 'Audit Trail' })).toHaveCount(0);
});

test('viewer sees authorized document navigation without upload controls', async ({ page }) => {
  await mockLogin(page, 'Viewer');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await expect(page).toHaveURL(/\/viewer\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'My documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Shared with me' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Upload documents' })).toHaveCount(0);
  await page.evaluate(() => {
    window.history.pushState({}, '', '/documents/upload');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/documents$/);
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/audit-trail');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/viewer\/dashboard$/);
});

test('dashboard loads live-data empty states and supports profile and password settings', async ({ page }) => {
  await mockLogin(page, 'Owner');
  await expect(page).toHaveURL(/\/owner\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Uploads over time' })).toBeVisible();
  await expect(page.getByText('Uploads will appear here when you add documents.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Profile' })).toHaveCount(0);
  await page.getByRole('navigation', { name: 'User navigation' }).getByRole('link', { name: 'Profile' }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await page.getByRole('button', { name: 'Edit profile' }).click();
  await page.getByLabel('Full name').fill('Updated Test User');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status')).toContainText('Profile changes saved.');
  const newPassword = page.getByLabel('New password');
  await expect(newPassword).toHaveAttribute('type', 'password');
  await page.getByRole('button', { name: 'Show new password' }).click();
  await expect(newPassword).toHaveAttribute('type', 'text');
  await newPassword.fill('SecurePassphrase12!');
  await expect(page.getByRole('img', { name: 'Password strength: Strong' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('navigation', { name: 'User navigation' })).toBeVisible();
});

test('owner upload, search and categories routes render distinct pages', async ({ page }) => {
  await mockLogin(page, 'Owner');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await navigation.getByRole('link', { name: 'Upload documents' }).click();
  await expect(page.getByRole('heading', { name: 'Upload documents' })).toBeVisible();
  await expect(page.getByText('Drag files here')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'My Documents' })).toHaveCount(0);

  await navigation.getByRole('link', { name: 'Search documents' }).click();
  await expect(page.getByRole('heading', { name: 'Search and Categories' })).toBeVisible();
  await expect(page.getByLabel('Document ID, name, or filename')).toBeVisible();

  await navigation.getByRole('link', { name: 'Categories' }).click();
  await expect(page.getByRole('heading', { name: 'Categories' })).toBeVisible();
});

test('shared documents page displays its explanatory empty state', async ({ page }) => {
  await mockLogin(page, 'Viewer');
  await page.getByRole('navigation', { name: 'User navigation' }).getByRole('link', { name: 'Shared with me' }).click();
  await expect(page.getByRole('heading', { name: 'Shared With Me' })).toBeVisible();
  await expect(page.getByText('No documents have been shared with you.')).toBeVisible();
});

test('failed server logout still clears local session and reports token expiry behavior', async ({ page }) => {
  await mockLogin(page, 'Owner');
  await page.route('**/api/v1/auth/logout', (route) => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('status')).toContainText('server revocation could not be confirmed');
});
