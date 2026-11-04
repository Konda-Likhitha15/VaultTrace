export type HealthStatus = { status: string };

export type RoleName = 'Administrator' | 'Owner' | 'Viewer';
export type User = {
  id: number;
  email: string;
  full_name: string;
  username: string;
  role: RoleName;
  account_status: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: User;
};

export type AdminOverview = {
  total_registered_users: number;
  total_active_users: number;
  total_pending_applications: number;
  total_approved_users: number;
  total_rejected_applications: number;
  total_owners: number;
  total_viewers: number;
};

export type AdminUser = {
  id: number;
  full_name: string;
  username: string;
  email: string;
  phone_number: string | null;
  role: RoleName;
  email_verified: boolean;
  account_status: string;
  registration_date: string;
  updated_at: string;
  organization_id: number | null;
};

export type AdminApplication = {
  id: number;
  user_id: number;
  full_name: string;
  username: string;
  email: string;
  phone_number: string | null;
  email_verified: boolean;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  submitted_at: string;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  assigned_role: RoleName | null;
  rejection_reason: string | null;
};

export type AdminActionResponse = { message: string; notification_sent: boolean | null };

export type AuditEvent = {
  id: number;
  actor_id: number | null;
  actor_email: string | null;
  actor_username: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  organization_id: number | null;
  organization_name: string | null;
  occurred_at: string;
  outcome: 'SUCCESS' | 'FAILURE';
  request_ip: string | null;
  user_agent: string | null;
  details: Record<string, unknown>;
  previous_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
};

export type AuditLogPage = { items: AuditEvent[]; total: number; limit: number; offset: number };
export type AuditSummary = { total_events: number; successful_operations: number; failed_operations: number; active_users: number };
export type AuditFilters = { user_id?: number; action?: string; search?: string; outcome?: 'SUCCESS' | 'FAILURE'; date_from?: string; date_to?: string; resource_id?: string; organization_id?: number };

export type DocumentMetadata = {
  id: string;
  document_name: string;
  original_filename: string;
  owner_id: number;
  category: string;
  description: string | null;
  file_extension: string;
  mime_type: string;
  file_size: number;
  checksum: string | null;
  visibility: 'PRIVATE' | 'SHARED' | 'RESTRICTED';
  current_version: number;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentSearchResult = DocumentMetadata & {
  owner_name: string;
  owner_username: string;
  access_level: 'READ' | 'EDIT' | 'OWNER';
};

export type DocumentPermission = {
  id: number;
  granted_to_user_id: number;
  recipient_username: string;
  recipient_name: string;
  recipient_email: string;
  permission_level: 'READ' | 'EDIT';
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
};

export type DocumentVersion = {
  id: string;
  version_number: number;
  original_filename: string;
  file_extension: string;
  mime_type: string;
  file_size: number;
  checksum: string | null;
  created_by_user_id: number;
  created_by_full_name: string;
  created_at: string;
};

export type DocumentActivity = {
  id: string;
  document_id: string | null;
  actor_user_id: number;
  actor_username: string;
  action: string;
  result: 'SUCCESS' | 'DENIED';
  details: Record<string, unknown>;
  created_at: string;
};

export type SharedDocument = {
  document: DocumentMetadata;
  owner_name: string;
  owner_username: string;
  shared_at: string;
  permission_level: 'READ' | 'EDIT';
  expires_at: string | null;
};

export type SharedByMe = {
  document_id: string;
  permission_id: number;
  document_name: string;
  recipient_user_id: number;
  recipient_name: string;
  recipient_username: string;
  permission_level: 'READ' | 'EDIT';
  shared_at: string;
  expires_at: string | null;
  revoked_at: string | null;
};

export type DocumentFilters = {
  search?: string;
  owner_id?: number;
  category?: string;
  file_type?: string;
  visibility?: 'PRIVATE' | 'SHARED' | 'RESTRICTED';
  access_status?: 'OWNED' | 'SHARED';
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
  sort_by?: 'created_at' | 'document_name' | 'file_size';
  sort_order?: 'asc' | 'desc';
};

export type EligibleShareUser = { id: number; full_name: string; username: string; email: string };
export type Organization = { id: number; name: string; member_count: number };
