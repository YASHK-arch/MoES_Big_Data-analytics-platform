// Operational Incident Intelligence Models

import {
  HazardCategoryCode,
  OverallReadiness,
  SeverityType,
  VerificationStatus,
} from './enums';
import { VerificationEventDetail } from './verification';

export interface IncidentLocation {
  name: string | null;
  latitude: number | null;
  longitude: number | null;
}

export interface IncidentCategory {
  code: HazardCategoryCode | string;
  title: string;
}

export interface IncidentMedia {
  id: string;
  media_type: string;
  url: string;
  sha256_hash?: string;
}

export interface IncidentCredibilitySummary {
  score: number | null;
  label: string;
  explanation: string;
  reason?: string | null;
  positive_drivers?: string[];
  negative_drivers?: string[];
  uncertainty_flags?: string[];
  is_machine_assessed: boolean;
}

export interface IncidentVerificationSummary {
  status: VerificationStatus;
  is_verified: boolean;
  is_rejected: boolean;
  is_under_review: boolean;
  is_duplicate: boolean;
  notes: string | null;
}

export interface IncidentIntelligenceSummary {
  overall_readiness: OverallReadiness;
  last_successful_stage: string | null;
}

export interface IncidentCorroborationCounts {
  evidence_count: number;
  observation_count: number;
  duplicate_cluster_size: number;
  is_cluster_representative: boolean;
}

export interface IncidentSummary {
  id: string;
  tracking_id: string;
  title: string;
  category: IncidentCategory;
  severity: SeverityType;
  location: IncidentLocation;
  occurred_at: string | null;
  verification_status: VerificationStatus;
  credibility_score: number | null;
  credibility_reason?: string | null;
  credibility_explanation?: Record<string, unknown> | null;
  readiness: OverallReadiness;
  media_count: number;
  created_at: string;
}

export interface IncidentDetailPublic {
  id: string;
  tracking_id: string;
  title: string;
  description: string | null;
  category: IncidentCategory;
  severity: SeverityType;
  location: IncidentLocation;
  occurred_at: string | null;
  credibility: IncidentCredibilitySummary;
  verification: IncidentVerificationSummary;
  intelligence_status: IncidentIntelligenceSummary;
  summaries: IncidentCorroborationCounts;
  media: IncidentMedia[];
  created_at: string;
}

export interface IncidentDetailOperator extends IncidentDetailPublic {
  verification_history: VerificationEventDetail[];
  orchestration_stages: Record<string, unknown>;
}

export interface IncidentListQueryParams {
  page?: number;
  page_size?: number;
  category?: string;
  severity?: SeverityType | string;
  verification_status?: string;
  min_credibility?: number;
  max_credibility?: number;
  readiness?: OverallReadiness | string;
  from_date?: string;
  to_date?: string;
  bbox?: string;
  sort_by?: 'occurred_at' | 'credibility_score' | 'created_at' | string;
  sort_order?: 'asc' | 'desc' | string;
}
