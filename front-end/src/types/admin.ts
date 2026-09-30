import { PaginationMeta } from './api';

export interface BulkVerificationPayload {
  incident_ids: string[];
  action: 'VERIFY' | 'REJECT';
  notes?: string;
  rejection_reason?: string;
}

export interface BulkVerificationResult {
  processed_count: number;
  action: string;
  affected_ids: string[];
}

export interface AuditLogEntry {
  id: string;
  user_id?: string | null;
  user_email?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  ip_address?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogListResponse {
  success: boolean;
  data: AuditLogEntry[];
  pagination: PaginationMeta;
  meta: Record<string, unknown>;
}

export interface ExportParams {
  limit?: number;
  category?: string;
  status?: string;
  severity?: string;
  hide_demo?: boolean;
}
