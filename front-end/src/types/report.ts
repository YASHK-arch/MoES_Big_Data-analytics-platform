import { SeverityType } from './enums';
import { PaginationMeta } from './api';
import { VerificationEventDetail } from './verification';

export interface WeatherCategoryOption {
  code: string;
  title: string;
  iconName: string;
  description?: string;
}

export interface CitizenReportFormValues {
  latitude: number;
  longitude: number;
  location_name?: string;
  category_code: string;
  severity: SeverityType;
  title: string;
  description?: string;
  occurred_at?: string;
  contact_name?: string;
  contact_info?: string;
}

export interface ReportSubmitData {
  id: string;
  tracking_id: string;
  processing_status: string;
  verification_status: string;
  submitted_at: string;
  media_count: number;
}

export interface ReportSubmitResponse {
  success: boolean;
  data: ReportSubmitData;
  meta: {
    timestamp: string;
    request_id?: string;
  };
}

export interface CategoryDetail {
  code: string;
  title: string;
}

export interface LocationDetail {
  name?: string | null;
  latitude: number;
  longitude: number;
}

export interface MediaDetail {
  id: string;
  media_type: string;
  url: string;
  sha256_hash: string;
}

export interface PhysicalCorroborationItem {
  id?: string;
  variable: string;
  observed_value?: number | null;
  unit: string;
  source: string;
  source_type: 'STATION' | 'MODEL' | string;
  station_or_grid_id?: string | null;
  distance_km?: number | null;
  time_gap_hours?: number | null;
  verdict: 'SUPPORTS' | 'CONTRADICTS' | 'NEUTRAL' | string;
  weight: number;
  contribution: number;
  provider_status: string;
  observation_time?: string | null;
  explanation?: string | null;
  is_simulated: boolean;
}

export interface PhysicalCorroborationBlock {
  overall_verdict: 'SUPPORTS' | 'CONTRADICTS' | 'NEUTRAL' | string;
  overall_provider_status: string;
  total_contribution: number;
  items: PhysicalCorroborationItem[];
  is_simulated: boolean;
}

export interface ReportDetailData {
  id: string;
  tracking_id: string;
  title: string;
  description?: string | null;
  category: CategoryDetail;
  severity: string;
  location: LocationDetail;
  occurred_at: string;
  processing_status: string;
  verification_status: string;
  credibility_score: number;
  credibility_reason?: string | null;
  is_demo?: boolean;
  media: MediaDetail[];
  verification_history?: VerificationEventDetail[];
  physical_corroboration?: PhysicalCorroborationBlock | null;
  physical_verdict?: string | null;
  created_at: string;
}

export interface ReportDetailResponse {
  success: boolean;
  data: ReportDetailData;
  meta: {
    timestamp: string;
    request_id?: string;
  };
}

export interface ReportListQueryParams {
  page?: number;
  page_size?: number;
  category?: string;
  severity?: SeverityType | string;
  status?: string;
  from_date?: string;
  to_date?: string;
  min_credibility?: number;
  bbox?: string;
  hide_demo?: boolean;
}

export interface ReportListResponse {
  success: boolean;
  data: ReportDetailData[];
  pagination: PaginationMeta;
  meta: {
    timestamp: string;
    request_id?: string;
  };
}
