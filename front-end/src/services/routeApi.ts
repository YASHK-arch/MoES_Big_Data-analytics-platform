// Route Blockage & Spatial Nearby API Client

import { ApiResponse, GeoJSONFeatureCollection } from '@/types';
import { apiClient } from './client';

export interface RoutePointInput {
  latitude: number;
  longitude: number;
  name?: string;
}

export interface RouteCheckRequest {
  origin: RoutePointInput;
  destination: RoutePointInput;
  corridor_km?: number;
}

export interface IntersectingHazardDetail {
  id: string;
  tracking_id: string;
  title: string;
  category_code: string;
  severity: string;
  verification_status: string;
  credibility_score: number;
  credibility_reason?: string;
  latitude: number;
  longitude: number;
  location_name?: string;
  distance_to_corridor_center_m: number;
  occurred_at: string;
}

export interface RouteCheckResponseData {
  is_blocked: boolean;
  hazard_count: number;
  corridor_km: number;
  highest_severity?: string;
  intersecting_incidents: IntersectingHazardDetail[];
  path_geojson: {
    type: string;
    features: Array<{
      type: string;
      geometry: Record<string, unknown>;
      properties: Record<string, unknown>;
    }>;
  };
}

export const routeApi = {
  /**
   * Check route corridor path for intersecting verified weather hazards.
   */
  async checkRoute(
    payload: RouteCheckRequest,
    signal?: AbortSignal
  ): Promise<ApiResponse<RouteCheckResponseData>> {
    return apiClient<ApiResponse<RouteCheckResponseData>>('/routes/check', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    });
  },

  /**
   * Fetch nearby GeoJSON incidents within radius_km around (lat, lng).
   */
  async getNearbyIncidents(
    lat: number,
    lng: number,
    radiusKm: number = 25.0,
    status?: string,
    signal?: AbortSignal
  ): Promise<GeoJSONFeatureCollection> {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
      radius_km: radiusKm.toString(),
    });
    if (status) params.append('status', status);
    return apiClient<GeoJSONFeatureCollection>(`/geo/incidents/nearby?${params.toString()}`, { signal });
  },

  /**
   * Fetch official IMD & NDMA forecast advisories and cyclone tracks.
   */
  async getForecastAdvisories(
    hazardType?: string,
    activeOnly: boolean = true,
    signal?: AbortSignal
  ): Promise<GeoJSONFeatureCollection> {
    const params = new URLSearchParams({
      active_only: activeOnly.toString(),
    });
    if (hazardType) params.append('hazard_type', hazardType);
    return apiClient<GeoJSONFeatureCollection>(`/geo/forecasts?${params.toString()}`, { signal });
  },
};
