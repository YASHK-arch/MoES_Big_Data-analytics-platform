// Operational Incident Intelligence API Client

import {
  ApiResponse,
  GeoJSONFeatureCollection,
  IncidentClusterDetailData,
  IncidentCredibilityData,
  IncidentDetailOperator,
  IncidentDetailPublic,
  IncidentEvidenceItemData,
  IncidentIntelligenceData,
  IncidentListQueryParams,
  IncidentObservationItemData,
  IncidentSummary,
  ReportDuplicateRequest,
  ReportRejectRequest,
  ReportReviewRequest,
  ReportVerifyRequest,
  VerificationQueueParams,
} from '@/types';
import { apiClient } from './client';

export const incidentApi = {
  /**
   * List & filter weather incidents with bounded server-side pagination.
   */
  async listIncidents(
    params: IncidentListQueryParams = {},
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentSummary[]>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.append('page', params.page.toString());
    if (params.page_size !== undefined) searchParams.append('page_size', params.page_size.toString());
    if (params.category && params.category !== 'ALL') searchParams.append('category', params.category);
    if (params.severity && params.severity !== 'ALL') searchParams.append('severity', params.severity);
    if (params.verification_status && params.verification_status !== 'ALL') {
      searchParams.append('verification_status', params.verification_status);
    }
    if (params.readiness && params.readiness !== 'ALL') searchParams.append('readiness', params.readiness);
    if (params.min_credibility !== undefined) searchParams.append('min_credibility', params.min_credibility.toString());
    if (params.max_credibility !== undefined) searchParams.append('max_credibility', params.max_credibility.toString());
    if (params.from_date) searchParams.append('from_date', params.from_date);
    if (params.to_date) searchParams.append('to_date', params.to_date);
    if (params.bbox) searchParams.append('bbox', params.bbox);
    if (params.sort_by) searchParams.append('sort_by', params.sort_by);
    if (params.sort_order) searchParams.append('sort_order', params.sort_order);
    if (params.hide_demo !== undefined) searchParams.append('hide_demo', params.hide_demo ? 'true' : 'false');

    const query = searchParams.toString();
    return apiClient<ApiResponse<IncidentSummary[]>>(`/incidents${query ? `?${query}` : ''}`, { signal });
  },

  /**
   * Retrieve bounded public incident detail.
   */
  async getIncidentDetail(
    id: string,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentDetailPublic>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailPublic>>(`/incidents/${cleanId}`, { signal });
  },

  /**
   * Retrieve full operational incident detail with verification audit history for operators.
   */
  async getIncidentOperatorDetail(
    id: string,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentDetailOperator>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailOperator>>(`/incidents/${cleanId}/operator-detail`, { signal });
  },

  /**
   * Retrieve machine credibility assessment and positive/negative drivers.
   */
  async getIncidentCredibility(
    id: string,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentCredibilityData>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentCredibilityData>>(`/incidents/${cleanId}/credibility`, { signal });
  },

  /**
   * Retrieve orchestration readiness and per-stage execution telemetry.
   */
  async getIncidentIntelligence(
    id: string,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentIntelligenceData>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentIntelligenceData>>(`/incidents/${cleanId}/intelligence`, { signal });
  },

  /**
   * Retrieve paginated digital evidence items linked to the incident.
   */
  async getIncidentEvidence(
    id: string,
    page: number = 1,
    pageSize: number = 20,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentEvidenceItemData[]>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentEvidenceItemData[]>>(
      `/incidents/${cleanId}/evidence?page=${page}&page_size=${pageSize}`,
      { signal }
    );
  },

  /**
   * Retrieve paginated physical observations (AWS/CWC) corroborating the incident.
   */
  async getIncidentObservations(
    id: string,
    page: number = 1,
    pageSize: number = 20,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentObservationItemData[]>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentObservationItemData[]>>(
      `/incidents/${cleanId}/observations?page=${page}&page_size=${pageSize}`,
      { signal }
    );
  },

  /**
   * Retrieve duplicate cluster topology and member list for the incident.
   */
  async getIncidentCluster(
    id: string,
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentClusterDetailData>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentClusterDetailData>>(`/incidents/${cleanId}/cluster`, { signal });
  },

  /**
   * Retrieve GeoJSON FeatureCollection bounded by PostGIS viewport or national overview.
   */
  async getGeoIncidents(
    bbox?: string,
    params: { status?: string; category?: string; hours_ago?: number; hide_demo?: boolean } = {},
    signal?: AbortSignal
  ): Promise<GeoJSONFeatureCollection> {
    const searchParams = new URLSearchParams();
    if (bbox) searchParams.append('bbox', bbox);
    if (params.status && params.status !== 'ALL') searchParams.append('status', params.status);
    if (params.category && params.category !== 'ALL') searchParams.append('category', params.category);
    if (params.hours_ago) searchParams.append('hours_ago', params.hours_ago.toString());
    if (params.hide_demo !== undefined) searchParams.append('hide_demo', params.hide_demo ? 'true' : 'false');

    const query = searchParams.toString();
    return apiClient<GeoJSONFeatureCollection>(`/geo/incidents${query ? `?${query}` : ''}`, { signal });
  },

  /**
   * Retrieve priority-ranked operator triage queue.
   */
  async getVerificationQueue(
    params: VerificationQueueParams = {},
    signal?: AbortSignal
  ): Promise<ApiResponse<IncidentSummary[]>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.append('page', params.page.toString());
    if (params.page_size !== undefined) searchParams.append('page_size', params.page_size.toString());
    if (params.priority && params.priority !== 'ALL') searchParams.append('priority', params.priority);
    if (params.category && params.category !== 'ALL') searchParams.append('category', params.category);
    if (params.jurisdiction) searchParams.append('jurisdiction', params.jurisdiction);

    const query = searchParams.toString();
    return apiClient<ApiResponse<IncidentSummary[]>>(`/verification/queue${query ? `?${query}` : ''}`, { signal });
  },

  /**
   * Authorize and verify incident.
   */
  async verifyIncident(
    id: string,
    payload: ReportVerifyRequest = {}
  ): Promise<ApiResponse<IncidentDetailOperator>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailOperator>>(`/verification/${cleanId}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Reject incident with mandatory reason code.
   */
  async rejectIncident(
    id: string,
    payload: ReportRejectRequest = {}
  ): Promise<ApiResponse<IncidentDetailOperator>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailOperator>>(`/verification/${cleanId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Mark incident as duplicate of another primary report.
   */
  async markDuplicateIncident(
    id: string,
    payload: ReportDuplicateRequest = {}
  ): Promise<ApiResponse<IncidentDetailOperator>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailOperator>>(`/verification/${cleanId}/mark-duplicate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Transition incident into active operator triage (UNDER_REVIEW).
   */
  async reviewIncident(
    id: string,
    payload: ReportReviewRequest = {}
  ): Promise<ApiResponse<IncidentDetailOperator>> {
    const cleanId = encodeURIComponent(id.trim());
    return apiClient<ApiResponse<IncidentDetailOperator>>(`/verification/${cleanId}/review`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
