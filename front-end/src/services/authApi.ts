/**
 * Authentication API Service for Citizen & Operator Access.
 */

import { apiClient } from './client';
import { ApiResponse } from '@/types';

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: 'CITIZEN' | 'OPERATOR' | 'ADMIN';
  jurisdiction_code?: string;
  home_location_lat?: number;
  home_location_lng?: number;
  home_location_name?: string;
  alert_radius_km?: number;
}

export type OperatorProfile = UserProfile;

export interface TokenResponseData {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: UserProfile;
  operator?: UserProfile;
}

export interface SignupPayload {
  email: string;
  password: string;
  full_name: string;
}

export interface UpdateLocationPayload {
  latitude: number;
  longitude: number;
  location_name?: string;
  alert_radius_km?: number;
}

export const authApi = {
  /**
   * Authenticates citizen or operator credentials and returns access token.
   */
  async login(username: string, password: string): Promise<ApiResponse<TokenResponseData>> {
    return apiClient<ApiResponse<TokenResponseData>>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  /**
   * Registers a new citizen account with automatic login.
   */
  async signup(payload: SignupPayload): Promise<ApiResponse<TokenResponseData>> {
    return apiClient<ApiResponse<TokenResponseData>>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Retrieves current authenticated user profile.
   */
  async getProfile(): Promise<UserProfile> {
    return apiClient<UserProfile>('/auth/me');
  },

  /**
   * Persists citizen home location and hazard radius.
   */
  async updateLocation(payload: UpdateLocationPayload): Promise<UserProfile> {
    return apiClient<UserProfile>('/citizen/me/location', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Retrieves list of reports submitted by the logged-in citizen.
   */
  async getMyReports(): Promise<{
    success: boolean;
    data: Array<{
      id: string;
      tracking_id: string;
      title: string;
      category: string;
      severity: string;
      verification_status: string;
      credibility_score: number;
      credibility_reason?: string;
      location_name?: string;
      latitude: number;
      longitude: number;
      occurred_at?: string;
    }>;
  }> {
    return apiClient('/citizen/my-reports');
  },
};
