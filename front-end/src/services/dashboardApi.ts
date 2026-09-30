// Dashboard Aggregation API Client

import { ApiResponse, DashboardSummaryData, DashboardSummaryQueryParams } from '@/types';
import { apiClient } from './client';

export const dashboardApi = {
  /**
   * Retrieve SQL-aggregated summary metrics for dashboard situational awareness.
   */
  async getSummary(
    params: DashboardSummaryQueryParams = {},
    signal?: AbortSignal
  ): Promise<ApiResponse<DashboardSummaryData>> {
    const searchParams = new URLSearchParams();
    if (params.time_range) searchParams.append('time_range', params.time_range);
    if (params.category && params.category !== 'ALL') searchParams.append('category', params.category);
    if (params.severity && params.severity !== 'ALL') searchParams.append('severity', params.severity);
    if (params.status && params.status !== 'ALL') searchParams.append('status', params.status);
    if (params.bbox) searchParams.append('bbox', params.bbox);
    if (params.hide_demo !== undefined) searchParams.append('hide_demo', params.hide_demo ? 'true' : 'false');

    const query = searchParams.toString();
    return apiClient<ApiResponse<DashboardSummaryData>>(`/dashboard/summary${query ? `?${query}` : ''}`, { signal });
  },
};
