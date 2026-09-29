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
  media: MediaDetail[];
  verification_history?: VerificationEventDetail[];
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
