// Presentation Helpers and Mapping Utilities

import {
  EvidenceRelationship,
  HazardCategoryCode,
  ObservationRelationship,
  OverallReadiness,
  SeverityType,
  StageOutcome,
  VerificationStatus,
} from '@/types';

export function formatHazardCategory(code?: HazardCategoryCode | string | null): string {
  if (!code) return 'Weather Incident';
  const clean = code.toUpperCase();
  switch (clean) {
    case 'FLOOD_WATERLOGGING':
      return 'Flood / Waterlogging';
    case 'HEAVY_RAINFALL':
      return 'Heavy Rainfall';
    case 'CYCLONE_STORM':
    case 'CYCLONE_GALE':
      return 'Cyclone / Storm';
    case 'URBAN_FLOOD':
      return 'Urban Inundation';
    case 'HEATWAVE':
    case 'EXTREME_HEAT':
      return 'Extreme Heatwave';
    case 'HAILSTORM':
      return 'Hailstorm';
    case 'LANDSLIDE':
      return 'Landslide / Mudslip';
    case 'THUNDERSTORM_LIGHTNING':
      return 'Thunderstorm & Lightning';
    case 'DROUGHT':
      return 'Drought Condition';
    case 'FOG':
      return 'Dense Fog';
    case 'DUST_STORM':
      return 'Dust Storm';
    case 'STRONG_WIND':
      return 'Strong Wind';
    case 'OTHER':
      return 'Weather Event';
    default:
      return code.replace(/_/g, ' ');
  }
}

export function formatSeverityBadge(severity?: SeverityType | string | null): {
  label: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
} {
  const clean = (severity || 'MODERATE').toUpperCase();
  switch (clean) {
    case 'SEVERE':
      return {
        label: 'Severe Impact',
        bgClass: 'bg-red-50 text-red-700',
        textClass: 'text-red-700',
        borderClass: 'border-red-200',
      };
    case 'HIGH':
      return {
        label: 'High Severity',
        bgClass: 'bg-orange-50 text-orange-700',
        textClass: 'text-orange-700',
        borderClass: 'border-orange-200',
      };
    case 'MODERATE':
      return {
        label: 'Moderate',
        bgClass: 'bg-amber-50 text-amber-700',
        textClass: 'text-amber-700',
        borderClass: 'border-amber-200',
      };
    case 'LOW':
    default:
      return {
        label: 'Low Impact',
        bgClass: 'bg-blue-50 text-blue-700',
        textClass: 'text-blue-700',
        borderClass: 'border-blue-200',
      };
  }
}

export function formatVerificationStatus(status?: VerificationStatus | string | null): {
  label: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
} {
  const clean = (status || 'PENDING').toUpperCase();
  switch (clean) {
    case 'VERIFIED':
      return {
        label: 'VERIFIED',
        bgClass: 'bg-emerald-600 text-white',
        textClass: 'text-emerald-700',
        borderClass: 'border-emerald-200',
      };
    case 'UNDER_REVIEW':
      return {
        label: 'UNDER REVIEW',
        bgClass: 'bg-amber-500 text-white',
        textClass: 'text-amber-700',
        borderClass: 'border-amber-200',
      };
    case 'REJECTED':
      return {
        label: 'REJECTED',
        bgClass: 'bg-rose-600 text-white',
        textClass: 'text-rose-700',
        borderClass: 'border-rose-200',
      };
    case 'DUPLICATE':
      return {
        label: 'DUPLICATE',
        bgClass: 'bg-indigo-600 text-white',
        textClass: 'text-indigo-700',
        borderClass: 'border-indigo-200',
      };
    case 'PENDING':
    default:
      return {
        label: 'PENDING',
        bgClass: 'bg-slate-700 text-white',
        textClass: 'text-slate-700',
        borderClass: 'border-slate-200',
      };
  }
}

export function formatReadiness(readiness?: OverallReadiness | string | null): {
  label: string;
  badgeClass: string;
  pillBg: string;
} {
  const clean = (readiness || 'INTELLIGENCE_PENDING').toUpperCase();
  switch (clean) {
    case 'INTELLIGENCE_READY':
      return {
        label: 'Intelligence Complete',
        badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        pillBg: 'bg-emerald-500',
      };
    case 'INTELLIGENCE_PARTIAL':
      return {
        label: 'Intelligence Partial (Enriching)',
        badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
        pillBg: 'bg-amber-500',
      };
    case 'INTELLIGENCE_FAILED':
      return {
        label: 'Intelligence Incomplete',
        badgeClass: 'bg-rose-50 text-rose-800 border-rose-200',
        pillBg: 'bg-rose-500',
      };
    case 'INTELLIGENCE_PENDING':
    default:
      return {
        label: 'Intelligence Queued',
        badgeClass: 'bg-sky-50 text-sky-800 border-sky-200',
        pillBg: 'bg-sky-500',
      };
  }
}

export function formatStageOutcome(outcome?: StageOutcome | string | null): {
  label: string;
  badgeClass: string;
} {
  const clean = (outcome || 'PENDING').toUpperCase();
  switch (clean) {
    case 'SUCCESS_WITH_RESULTS':
      return {
        label: 'Results Found',
        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'SUCCESS_WITH_NO_MATCH':
      return {
        label: 'No Matches Found',
        badgeClass: 'bg-slate-50 text-slate-700 border-slate-200',
      };
    case 'SUCCESS_WITH_INSUFFICIENT_DATA':
      return {
        label: 'Insufficient Data',
        badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
      };
    case 'SKIPPED_NOT_APPLICABLE':
      return {
        label: 'Not Applicable',
        badgeClass: 'bg-slate-50 text-slate-500 border-slate-200',
      };
    case 'SKIPPED_STALE':
      return {
        label: 'Skipped (Stale Target)',
        badgeClass: 'bg-slate-50 text-slate-500 border-slate-200',
      };
    case 'RETRYABLE_FAILURE':
      return {
        label: 'Retrying Execution',
        badgeClass: 'bg-sky-50 text-sky-700 border-sky-200 animate-pulse',
      };
    case 'PERMANENT_FAILURE':
      return {
        label: 'Processing Incomplete',
        badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',
      };
    default:
      return {
        label: clean.replace(/_/g, ' '),
        badgeClass: 'bg-slate-50 text-slate-600 border-slate-200',
      };
  }
}

export function formatEvidenceRelationship(rel?: EvidenceRelationship | string | null): {
  label: string;
  badgeClass: string;
} {
  const clean = (rel || 'RELATED').toUpperCase();
  switch (clean) {
    case 'SUPPORTING':
      return {
        label: 'Supporting Evidence',
        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'RELATED':
      return {
        label: 'Related Reporting',
        badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
      };
    case 'CONTEXTUAL':
      return {
        label: 'Contextual Reference',
        badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
      };
    case 'CONTRADICTORY':
      return {
        label: 'Contradictory Source',
        badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',
      };
    case 'IRRELEVANT':
    default:
      return {
        label: 'Non-Pertinent',
        badgeClass: 'bg-slate-50 text-slate-500 border-slate-200',
      };
  }
}

export function formatObservationRelationship(rel?: ObservationRelationship | string | null): {
  label: string;
  badgeClass: string;
} {
  const clean = (rel || 'CONSISTENT').toUpperCase();
  switch (clean) {
    case 'CORROBORATING':
      return {
        label: 'Physical Corroboration',
        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'CONSISTENT':
      return {
        label: 'Consistent Baseline',
        badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
      };
    case 'WEAK':
      return {
        label: 'Weak Association',
        badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
      };
    case 'CONTRADICTORY':
      return {
        label: 'Physical Contradiction',
        badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',
      };
    case 'INSUFFICIENT_DATA':
    default:
      return {
        label: 'Insufficient Station Data',
        badgeClass: 'bg-slate-50 text-slate-500 border-slate-200',
      };
  }
}

export function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return 'Recent';
  try {
    const diffMs = Date.now() - new Date(dateStr).getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return 'Recent';
  }
}

export function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return 'Unknown';
  try {
    const d = new Date(dateStr);
    return d.toLocaleString([], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }) + ' UTC';
  } catch {
    return dateStr;
  }
}
