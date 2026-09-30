import {
  AuditLogListResponse,
  BulkVerificationPayload,
  BulkVerificationResult,
  ExportParams,
} from '@/types';
import { API_BASE_URL, apiClient } from './client';

export const adminApi = {
  /**
   * Bulk verify or reject reports in an atomic transaction (max 100).
   */
  async bulkVerification(
    payload: BulkVerificationPayload
  ): Promise<{ success: boolean; data: BulkVerificationResult }> {
    return apiClient<{ success: boolean; data: BulkVerificationResult }>(
      '/admin/verification/bulk',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  /**
   * Fetch paginated audit logs.
   */
  async getAuditLogs(
    params: {
      page?: number;
      page_size?: number;
      action?: string;
      entity_type?: string;
      user_id?: string;
    } = {},
    signal?: AbortSignal
  ): Promise<AuditLogListResponse> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.append('page', params.page.toString());
    if (params.page_size !== undefined) searchParams.append('page_size', params.page_size.toString());
    if (params.action) searchParams.append('action', params.action);
    if (params.entity_type) searchParams.append('entity_type', params.entity_type);
    if (params.user_id) searchParams.append('user_id', params.user_id);

    const query = searchParams.toString();
    return apiClient<AuditLogListResponse>(`/admin/audit-logs${query ? `?${query}` : ''}`, {
      signal,
    });
  },

  /**
   * Stream and download CSV or GeoJSON incident export.
   */
  async downloadExport(format: 'csv' | 'geojson', params: ExportParams = {}): Promise<void> {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.append('limit', params.limit.toString());
    if (params.category && params.category !== 'ALL') searchParams.append('category', params.category);
    if (params.status && params.status !== 'ALL') searchParams.append('status', params.status);
    if (params.severity && params.severity !== 'ALL') searchParams.append('severity', params.severity);
    if (params.hide_demo !== undefined) {
      searchParams.append('hide_demo', params.hide_demo ? 'true' : 'false');
    }

    const query = searchParams.toString();
    const endpoint = `/admin/export/${format}${query ? `?${query}` : ''}`;
    const url = `${API_BASE_URL}${endpoint}`;

    const token =
      typeof sessionStorage !== 'undefined'
        ? sessionStorage.getItem('nwbda_auth_token')
        : null;

    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Export failed with HTTP ${res.status}`);
    }

    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `incidents_export_${Date.now()}.${format === 'csv' ? 'csv' : 'geojson'}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(blobUrl);
  },
};
