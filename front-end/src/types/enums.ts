// Canonical Domain & Operational Enums mirroring backend models

export type SeverityType = 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE';

export type VerificationStatus =
  | 'PENDING'
  | 'UNDER_REVIEW'
  | 'VERIFIED'
  | 'REJECTED'
  | 'DUPLICATE';

export type OverallReadiness =
  | 'INTELLIGENCE_READY'
  | 'INTELLIGENCE_PARTIAL'
  | 'INTELLIGENCE_PENDING'
  | 'INTELLIGENCE_FAILED';

export type StageName =
  | 'LOCATION'
  | 'DUPLICATE'
  | 'EVIDENCE'
  | 'OBSERVATION'
  | 'CREDIBILITY';

export type StageOutcome =
  | 'SUCCESS_WITH_RESULTS'
  | 'SUCCESS_WITH_NO_MATCH'
  | 'SUCCESS_WITH_INSUFFICIENT_DATA'
  | 'SKIPPED_NOT_APPLICABLE'
  | 'SKIPPED_STALE'
  | 'RETRYABLE_FAILURE'
  | 'PERMANENT_FAILURE';

export type EvidenceRelationship =
  | 'SUPPORTING'
  | 'RELATED'
  | 'CONTEXTUAL'
  | 'CONTRADICTORY'
  | 'IRRELEVANT';

export type ObservationRelationship =
  | 'CORROBORATING'
  | 'CONSISTENT'
  | 'WEAK'
  | 'CONTRADICTORY'
  | 'IRRELEVANT'
  | 'INSUFFICIENT_DATA';

export type HazardCategoryCode =
  | 'FLOOD_WATERLOGGING'
  | 'HEAVY_RAINFALL'
  | 'THUNDERSTORM_LIGHTNING'
  | 'CYCLONE_STORM'
  | 'HEATWAVE'
  | 'HAILSTORM'
  | 'LANDSLIDE'
  | 'DROUGHT'
  | 'URBAN_FLOOD'
  | 'FOG'
  | 'DUST_STORM'
  | 'STRONG_WIND'
  | 'OTHER'
  | 'EXTREME_HEAT'
  | 'CYCLONE_GALE';

export interface HazardCategoryMeta {
  code: HazardCategoryCode;
  label: string;
  color: string;
  icon: string;
}

export const HAZARD_CATEGORIES: Record<string, HazardCategoryMeta> = {
  FLOOD_WATERLOGGING: {
    code: 'FLOOD_WATERLOGGING',
    label: 'Flood & Waterlogging',
    color: '#0284c7',
    icon: 'droplet',
  },
  HEAVY_RAINFALL: {
    code: 'HEAVY_RAINFALL',
    label: 'Heavy Rainfall',
    color: '#2563eb',
    icon: 'cloud-rain',
  },
  THUNDERSTORM_LIGHTNING: {
    code: 'THUNDERSTORM_LIGHTNING',
    label: 'Thunderstorm & Lightning',
    color: '#eab308',
    icon: 'zap',
  },
  CYCLONE_STORM: {
    code: 'CYCLONE_STORM',
    label: 'Cyclone & Storm',
    color: '#7c3aed',
    icon: 'wind',
  },
  CYCLONE_GALE: {
    code: 'CYCLONE_STORM',
    label: 'Cyclone & Storm',
    color: '#7c3aed',
    icon: 'wind',
  },
  HEATWAVE: {
    code: 'HEATWAVE',
    label: 'Heatwave',
    color: '#ef4444',
    icon: 'thermometer-sun',
  },
  EXTREME_HEAT: {
    code: 'HEATWAVE',
    label: 'Extreme Heatwave',
    color: '#ef4444',
    icon: 'thermometer-sun',
  },
  HAILSTORM: {
    code: 'HAILSTORM',
    label: 'Hailstorm',
    color: '#06b6d4',
    icon: 'cloud-hail',
  },
  LANDSLIDE: {
    code: 'LANDSLIDE',
    label: 'Landslide & Mudslip',
    color: '#b45309',
    icon: 'mountain',
  },
  DROUGHT: {
    code: 'DROUGHT',
    label: 'Drought Condition',
    color: '#d97706',
    icon: 'sun',
  },
  URBAN_FLOOD: {
    code: 'URBAN_FLOOD',
    label: 'Urban Inundation',
    color: '#0284c7',
    icon: 'waves',
  },
  FOG: {
    code: 'FOG',
    label: 'Dense Fog',
    color: '#64748b',
    icon: 'cloud-fog',
  },
  DUST_STORM: {
    code: 'DUST_STORM',
    label: 'Dust Storm',
    color: '#a16207',
    icon: 'sparkles',
  },
  STRONG_WIND: {
    code: 'STRONG_WIND',
    label: 'Strong Wind & Gale',
    color: '#0d9488',
    icon: 'wind',
  },
  OTHER: {
    code: 'OTHER',
    label: 'Other Weather Incident',
    color: '#6b7280',
    icon: 'help-circle',
  },
};

export type RejectionReasonCode =
  | 'INACCURATE_LOCATION'
  | 'HOAX_SPAM'
  | 'NORMAL_WEATHER'
  | 'OUTDATED_EVENT'
  | 'OTHER';
