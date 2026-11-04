import axios from 'axios';
import type { AdminActionResponse, AdminApplication, AdminOverview, AdminUser, AuditFilters, AuditLogPage, AuditSummary, DocumentActivity, DocumentFilters, DocumentMetadata, DocumentPermission, DocumentSearchResult, DocumentVersion, EligibleShareUser, Organization, SharedByMe, SharedDocument, TokenResponse, User } from '../types';

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8000/api/v1';
export const api = axios.create({ baseURL: configuredBaseUrl.replace(/\/+$/, ''), timeout: 30_000 });

export async function apiErrorMessage(error: unknown, fallback = 'The request could not be completed.'): Promise<string> {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback;
  let body: unknown = error.response?.data;
  if (typeof Blob !== 'undefined' && body instanceof Blob) {
    try { body = JSON.parse(await body.text()) as unknown; } catch { body = undefined; }
  }
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item: unknown) => item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string' ? [item.msg] : []);
      if (messages.length) return messages.join(' ');
    }
  }
  if (!error.response) {
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return `The API request timed out at ${configuredBaseUrl}. Check that the backend and database are healthy.`;
    return `No response from ${configuredBaseUrl}. Confirm that the backend is listening and the browser can reach it.`;
  }
  const details: Record<number, string> = { 401: 'Your session expired or is invalid. Sign in again.', 403: 'Your account is not authorized to perform this action.', 404: 'The requested resource was not found.', 500: 'The backend encountered an internal error. Check backend logs.' };
  return details[error.response.status] || `The API returned HTTP ${error.response.status}.`;
}

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const headers = axios.isAxiosError(error) ? error.config?.headers as Record<string, unknown> | undefined : undefined;
    const hasAuthorization = Boolean(headers?.Authorization ?? headers?.authorization);
    if (axios.isAxiosError(error) && error.response?.status === 401 && hasAuthorization && !error.config?.url?.includes('/auth/login') && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('vaulttrace:unauthorized'));
    }
    return Promise.reject(error);
  },
);

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await api.post('/auth/login', { email, password });
  return response.data as TokenResponse;
}

export async function logout(token: string): Promise<void> {
  await api.post('/auth/logout', undefined, { headers: { Authorization: `Bearer ${token}` } });
}

export async function loadCurrentUser(token: string) {
  const response = await api.get('/users/me', { headers: { Authorization: `Bearer ${token}` } });
  return response.data as User;
}

export async function requestEmailOtp(email: string, resend = false): Promise<void> {
  void resend;
  await api.post('/auth/signup/send-otp', { email });
}

export async function verifyEmailOtp(email: string, otp: string): Promise<void> {
  await api.post('/auth/signup/verify-otp', { email, otp });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await api.post('/auth/forgot-password', { email });
}

export async function verifyPasswordResetOtp(email: string, otp: string): Promise<{ authorization_token: string; expires_in_seconds: number }> {
  return (await api.post('/auth/verify-reset-otp', { email, otp })).data;
}

export async function submitPasswordReset(authorization_token: string, password: string, confirm_password: string): Promise<void> {
  await api.post('/auth/reset-password', { authorization_token, password, confirm_password });
}

export async function submitRegistration(payload: {
  full_name: string;
  username: string;
  email: string;
  phone_number?: string;
  password: string;
  confirm_password: string;
}): Promise<{ message: string; application_id: number; approval_status: string }> {
  const response = await api.post('/auth/register', payload);
  return response.data;
}

function authHeaders(token: string) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function getAdminOverview(token: string): Promise<AdminOverview> {
  return (await api.get('/admin/dashboard', authHeaders(token))).data as AdminOverview;
}

export async function getAuditLogs(token: string, filters: AuditFilters, offset: number, limit = 25): Promise<AuditLogPage> {
  return (await api.get('/admin/audit-logs', { ...authHeaders(token), params: { ...filters, offset, limit, sort_order: 'desc' } })).data as AuditLogPage;
}

export async function getAuditSummary(token: string, filters: AuditFilters): Promise<AuditSummary> {
  return (await api.get('/admin/audit-logs/summary', { ...authHeaders(token), params: filters })).data as AuditSummary;
}

export async function exportAuditLogs(token: string, filters: AuditFilters): Promise<Blob> {
  return (await api.get('/admin/audit-logs/export.csv', { ...authHeaders(token), params: filters, responseType: 'blob' })).data as Blob;
}

export async function getAdminUsers(token: string): Promise<AdminUser[]> {
  return (await api.get('/admin/users', authHeaders(token))).data as AdminUser[];
}

export async function getAdminApplications(token: string): Promise<AdminApplication[]> {
  return (await api.get('/admin/applications', authHeaders(token))).data as AdminApplication[];
}

export async function approveAdminApplication(token: string, id: number, role: 'Owner' | 'Viewer'): Promise<AdminActionResponse> {
  return (await api.post(`/admin/applications/${id}/approve`, { role }, authHeaders(token))).data as AdminActionResponse;
}

export async function rejectAdminApplication(token: string, id: number, reason: string): Promise<AdminActionResponse> {
  return (await api.post(`/admin/applications/${id}/reject`, { reason }, authHeaders(token))).data as AdminActionResponse;
}

export async function updateAdminUserRole(token: string, id: number, role: 'Owner' | 'Viewer'): Promise<AdminUser> {
  return (await api.patch(`/admin/users/${id}/role`, { role }, authHeaders(token))).data as AdminUser;
}

export async function updateAdminUserStatus(token: string, id: number, status: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED'): Promise<AdminUser> {
  return (await api.patch(`/admin/users/${id}/status`, { status }, authHeaders(token))).data as AdminUser;
}

export async function getDocuments(token: string, filters: DocumentFilters = {}): Promise<DocumentMetadata[]> {
  return (await api.get('/documents/', { ...authHeaders(token), params: filters })).data as DocumentMetadata[];
}

export async function searchDocuments(token: string, filters: DocumentFilters = {}): Promise<DocumentSearchResult[]> {
  return (await api.get('/documents/search', { ...authHeaders(token), params: filters })).data as DocumentSearchResult[];
}

export async function getDocumentCategories(token: string): Promise<string[]> {
  return (await api.get('/documents/categories', authHeaders(token))).data as string[];
}

export async function getSharedWithMe(token: string): Promise<SharedDocument[]> {
  return (await api.get('/documents/shared-with-me', authHeaders(token))).data as SharedDocument[];
}

export async function getSharedByMe(token: string): Promise<SharedByMe[]> {
  return (await api.get('/documents/shared-by-me', authHeaders(token))).data as SharedByMe[];
}

export async function getDeletedDocuments(token: string): Promise<DocumentMetadata[]> {
  return (await api.get('/documents/deleted', authHeaders(token))).data as DocumentMetadata[];
}

export async function uploadDocument(
  token: string,
  file: File,
  fields: { document_name: string; category: string; description?: string; visibility?: 'PRIVATE' | 'SHARED' | 'RESTRICTED' },
  onProgress: (percent: number) => void,
): Promise<DocumentMetadata> {
  const body = new FormData();
  body.append('file', file);
  body.append('document_name', fields.document_name);
  body.append('category', fields.category);
  if (fields.description) body.append('description', fields.description);
  if (fields.visibility) body.append('visibility', fields.visibility);
  return (await api.post('/documents/upload', body, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 120_000,
    onUploadProgress: (event) => {
      if (event.total) onProgress(Math.round((event.loaded / event.total) * 100));
    },
  })).data as DocumentMetadata;
}

export async function searchDocumentPreview(token: string, documentId: string): Promise<Blob> {
  return (await api.get(`/documents/${documentId}/preview`, { ...authHeaders(token), responseType: 'blob' })).data as Blob;
}

export async function updateDocumentMetadata(token: string, documentId: string, patch: { document_name?: string; category?: string; description?: string | null; visibility?: 'PRIVATE' | 'SHARED' | 'RESTRICTED' }): Promise<DocumentMetadata> {
  return (await api.patch(`/documents/${documentId}`, patch, authHeaders(token))).data as DocumentMetadata;
}

export async function uploadDocumentVersion(token: string, documentId: string, file: File, onProgress: (percent: number) => void): Promise<DocumentVersion> {
  const body = new FormData();
  body.append('file', file);
  return (await api.post(`/documents/${documentId}/versions`, body, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 120_000,
    onUploadProgress: (event) => { if (event.total) onProgress(Math.round((event.loaded / event.total) * 100)); },
  })).data as DocumentVersion;
}

export async function getDocumentVersions(token: string, documentId: string): Promise<DocumentVersion[]> {
  return (await api.get(`/documents/${documentId}/versions`, authHeaders(token))).data as DocumentVersion[];
}

export async function downloadDocumentVersion(token: string, documentId: string, versionId: string): Promise<Blob> {
  return (await api.get(`/documents/${documentId}/versions/${versionId}/download`, { ...authHeaders(token), responseType: 'blob' })).data as Blob;
}

export async function getDocumentPermissions(token: string, documentId: string): Promise<DocumentPermission[]> {
  return (await api.get(`/documents/${documentId}/permissions`, authHeaders(token))).data as DocumentPermission[];
}

export async function searchEligibleShareUsers(token: string, documentId: string, q: string): Promise<EligibleShareUser[]> {
  return (await api.get(`/documents/${documentId}/eligible-users`, { ...authHeaders(token), params: { q } })).data as EligibleShareUser[];
}

export async function getAdminOrganizations(token: string): Promise<Organization[]> {
  return (await api.get('/admin/organizations', authHeaders(token))).data as Organization[];
}

export async function createAdminOrganization(token: string, name: string): Promise<Organization> {
  return (await api.post('/admin/organizations', { name }, authHeaders(token))).data as Organization;
}

export async function assignUserOrganization(token: string, userId: number, organizationId: number | null): Promise<AdminUser> {
  return (await api.patch(`/admin/users/${userId}/organization`, { organization_id: organizationId }, authHeaders(token))).data as AdminUser;
}

export async function grantDocumentPermission(token: string, documentId: string, payload: { recipient_email?: string; recipient_user_id?: number; permission_level: 'READ' | 'EDIT'; expires_at?: string | null }): Promise<DocumentPermission> {
  return (await api.post(`/documents/${documentId}/permissions`, payload, authHeaders(token))).data as DocumentPermission;
}

export async function updateDocumentPermission(token: string, documentId: string, permissionId: number, payload: { permission_level?: 'READ' | 'EDIT'; expires_at?: string | null }): Promise<DocumentPermission> {
  return (await api.patch(`/documents/${documentId}/permissions/${permissionId}`, payload, authHeaders(token))).data as DocumentPermission;
}

export async function revokeDocumentPermission(token: string, documentId: string, permissionId: number): Promise<void> {
  await api.delete(`/documents/${documentId}/permissions/${permissionId}`, authHeaders(token));
}

export async function getDocumentActivity(token: string, documentId: string): Promise<DocumentActivity[]> {
  return (await api.get(`/documents/${documentId}/activity`, authHeaders(token))).data as DocumentActivity[];
}

export async function restoreDocument(token: string, documentId: string): Promise<DocumentMetadata> {
  return (await api.post(`/documents/${documentId}/restore`, undefined, authHeaders(token))).data as DocumentMetadata;
}

export async function getAdminDocuments(token: string, search?: string) {
  return (await api.get('/admin/documents', { ...authHeaders(token), params: { search } })).data as Array<{
    id: string; document_name: string; original_filename: string; owner_id: number; owner_name: string;
    owner_username: string; category: string; file_extension: string; mime_type: string; file_size: number;
    visibility: string; current_version: number; deleted_at: string | null; created_at: string; updated_at: string;
  }>;
}

export async function getAdminDocumentAudit(token: string, documentId?: string): Promise<DocumentActivity[]> {
  return (await api.get('/admin/documents/audit', { ...authHeaders(token), params: { document_id: documentId } })).data as DocumentActivity[];
}

export async function getAdminDocumentPermissions(token: string, documentId?: string) {
  return (await api.get('/admin/documents/permissions', { ...authHeaders(token), params: { document_id: documentId } })).data as Array<{
    id: number; document_id: string; document_name: string; owner_id: number; recipient_user_id: number;
    recipient_username: string; permission_level: 'VIEWER' | 'EDITOR' | 'OWNER'; created_at: string;
    expires_at: string | null; revoked_at: string | null;
  }>;
}

export async function revokeAdminDocumentPermission(token: string, permissionId: number): Promise<void> {
  await api.delete(`/admin/documents/permissions/${permissionId}`, authHeaders(token));
}

export async function downloadDocument(token: string, documentId: string): Promise<Blob> {
  return (await api.get(`/documents/${documentId}/download`, {
    ...authHeaders(token),
    responseType: 'blob',
  })).data as Blob;
}

export async function deleteDocument(token: string, documentId: string): Promise<void> {
  await api.delete(`/documents/${documentId}`, authHeaders(token));
}
