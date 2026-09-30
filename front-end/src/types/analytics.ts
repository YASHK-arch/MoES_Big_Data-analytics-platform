// Dashboard and Analytics Aggregation Contracts (Matching Backend Schemas)

export interface VerificationBreakdown {
  verified_count: number;
  verified_rate: number;
  pending_count: number;
  under_review_count: number;
  rejected_count: number;
  duplicate_count: number;
}

export interface SeverityBreakdown {
  severe_high_count: number;
  severe_count: number;
  high_count: number;
  moderate_count: number;
  low_count: number;
}

export interface CategoryDistributionItem {
  category_code: string;
  category_name: string;
  count: number;
  percentage: number;
}

export interface DiurnalDistributionItem {
  window: string;
  label: string;
  count: number;
}

export interface DashboardSummaryData {
  total_count: number;
  period_count: number;
  count_24h: number;
  last_24h_pct: number;
  verification: VerificationBreakdown;
  severity: SeverityBreakdown;
  category_distribution: CategoryDistributionItem[];
  diurnal_distribution: DiurnalDistributionItem[];
}

export interface DashboardSummaryQueryParams {
  time_range?: '24h' | '48h' | '7d' | '30d' | 'all' | string;
  category?: string;
  severity?: string;
  status?: string;
  bbox?: string;
  hide_demo?: boolean;
}

export interface AnalyticsTrendBucket {
  bucket: string;
  label: string;
  total: number;
  verified: number;
}

export interface AnalyticsTrendData {
  time_range: string;
  interval: string;
  buckets: AnalyticsTrendBucket[];
}

export interface AnalyticsTrendQueryParams {
  time_range?: '24h' | '7d' | '30d' | 'all' | string;
  interval?: 'hour' | 'day' | string;
  category?: string;
  severity?: string;
  status?: string;
  bbox?: string;
}

export interface RegionalDistributionItem {
  region_code: string;
  region_name: string;
  count: number;
  percentage: number;
}

export interface AnalyticsRegionalData {
  time_range: string;
  total_classified: number;
  regions: RegionalDistributionItem[];
}

export interface AnalyticsRegionalQueryParams {
  time_range?: '24h' | '7d' | '30d' | 'all' | string;
  category?: string;
  severity?: string;
  status?: string;
  bbox?: string;
}
