import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { MobileBottomNav } from '@/components/layout/MobileBottomNav';
import {
  AnalyticsFilters,
  AnalyticsFilterState,
  AnalyticsKpiCards,
  ReportActivityChart,
  EventDistributionCard,
  SeverityDistributionCard,
  RecentReportsTable,
  VerificationStatusCard,
  RegionalActivityCard,
  ObservedPatternsCard,
  GEOGRAPHY_OPTIONS,
} from '@/features/analytics';
import { incidentApi } from '@/services/incidentApi';
import { dashboardApi } from '@/services/dashboardApi';
import { analyticsApi } from '@/services/analyticsApi';
import { incidentKeys, dashboardKeys, analyticsKeys } from '@/lib/queryKeys';
import {
  AnalyticsRegionalQueryParams,
  AnalyticsTrendQueryParams,
  DashboardSummaryQueryParams,
  IncidentListQueryParams,
} from '@/types';
import { useLocationScope } from '@/hooks';
import { BarChart3, Filter, AlertCircle, MapPin, Globe } from 'lucide-react';

export const AnalyticsPage: React.FC = () => {
  const { currentLocation, isDefault } = useLocationScope();

  const [filters, setFilters] = useState<AnalyticsFilterState>({
    timeRange: '7d',
    category: 'ALL',
    severity: 'ALL',
    status: 'ALL',
    region: 'ALL',
  });

  const [tempFilters, setTempFilters] = useState<AnalyticsFilterState>(filters);
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  // Compute effective bounding box
  const effectiveBbox = useMemo(() => {
    if (filters.region !== 'ALL' && GEOGRAPHY_OPTIONS[filters.region]?.bbox) {
      return GEOGRAPHY_OPTIONS[filters.region].bbox;
    }
    return currentLocation.bbox || undefined;
  }, [filters.region, currentLocation.bbox]);

  // 1. Summary Metrics Query (dashboardApi.getSummary)
  const summaryParams = useMemo<DashboardSummaryQueryParams>(() => {
    const params: DashboardSummaryQueryParams = {};

    if (filters.timeRange) {
      params.time_range = filters.timeRange;
    }
    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }
    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }
    if (filters.status !== 'ALL') {
      params.status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }

    return params;
  }, [filters, effectiveBbox]);

  const {
    data: summaryResponse,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    error: summaryError,
    isFetching: isSummaryFetching,
  } = useQuery({
    queryKey: dashboardKeys.summary(summaryParams as Record<string, unknown>),
    queryFn: ({ signal }) => dashboardApi.getSummary(summaryParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const summaryData = summaryResponse?.data;

  // 2. Activity Trends Query (analyticsApi.getTrends)
  const trendParams = useMemo<AnalyticsTrendQueryParams>(() => {
    const params: AnalyticsTrendQueryParams = {};

    if (filters.timeRange) {
      params.time_range = filters.timeRange;
    }
    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }
    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }
    if (filters.status !== 'ALL') {
      params.status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }

    return params;
  }, [filters, effectiveBbox]);

  const {
    data: trendResponse,
    isLoading: isTrendLoading,
    isError: isTrendError,
    error: trendError,
  } = useQuery({
    queryKey: analyticsKeys.trends(trendParams as Record<string, unknown>),
    queryFn: ({ signal }) => analyticsApi.getTrends(trendParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const trendData = trendResponse?.data;

  // 3. Regional Activity Distribution Query (analyticsApi.getRegional)
  const regionalParams = useMemo<AnalyticsRegionalQueryParams>(() => {
    const params: AnalyticsRegionalQueryParams = {};

    if (filters.timeRange) {
      params.time_range = filters.timeRange;
    }
    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }
    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }
    if (filters.status !== 'ALL') {
      params.status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }

    return params;
  }, [filters, effectiveBbox]);

  const {
    data: regionalResponse,
    isLoading: isRegionalLoading,
    isError: isRegionalError,
    error: regionalError,
  } = useQuery({
    queryKey: analyticsKeys.regional(regionalParams as Record<string, unknown>),
    queryFn: ({ signal }) => analyticsApi.getRegional(regionalParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const regionalData = regionalResponse?.data;

  // 4. Recent Incidents Query (Optimized single-page fetch for RecentReportsTable)
  const recentParams = useMemo<IncidentListQueryParams>(() => {
    const params: IncidentListQueryParams = {
      page: 1,
      page_size: 8,
      sort_by: 'occurred_at',
      sort_order: 'desc',
    };

    const now = new Date();
    if (filters.timeRange === '24h') {
      params.from_date = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
    } else if (filters.timeRange === '7d') {
      params.from_date = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
    } else if (filters.timeRange === '30d') {
      params.from_date = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
    }

    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }
    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }
    if (filters.status !== 'ALL') {
      params.verification_status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }

    return params;
  }, [filters, effectiveBbox]);

  const {
    data: recentResponse,
    isLoading: isRecentLoading,
    isError: isRecentError,
    error: recentError,
  } = useQuery({
    queryKey: incidentKeys.list(recentParams as Record<string, unknown>),
    queryFn: ({ signal }) => incidentApi.listIncidents(recentParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const recentIncidents = recentResponse?.data || [];

  const handleApplyFilters = () => {
    setFilters(tempFilters);
    setMobileFilterOpen(false);
  };

  const handleResetFilters = () => {
    const defaultState: AnalyticsFilterState = {
      timeRange: '7d',
      category: 'ALL',
      severity: 'ALL',
      status: 'ALL',
      region: 'ALL',
    };
    setTempFilters(defaultState);
    setFilters(defaultState);
    setMobileFilterOpen(false);
  };

  const isAnyError = isRegionalError || isTrendError || isSummaryError || isRecentError;
  const activeError = summaryError || trendError || regionalError || recentError;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Navbar />

      <main className="flex-1 pb-16 pt-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
          {/* Header Banner */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
                  <BarChart3 className="h-4 w-4" />
                </div>
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
                  Weather Analytics
                </h1>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                Explore report activity, event distribution, severity patterns, and verification trends across the selected period.
              </p>
            </div>

            {/* Mobile Filters Toggle Button */}
            <div className="block md:hidden">
              <button
                type="button"
                onClick={() => setMobileFilterOpen(!mobileFilterOpen)}
                className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-2xs hover:bg-slate-50 cursor-pointer"
              >
                <Filter className="h-3.5 w-3.5 text-blue-600" />
                <span>Filters</span>
              </button>
            </div>
          </div>

          {/* Location Scope Indicator Banner */}
          <div className="flex items-center justify-between rounded-xl bg-blue-50/80 border border-blue-200/80 px-3.5 py-2 text-xs text-blue-900 shadow-2xs">
            <div className="flex items-center space-x-2">
              {isDefault ? (
                <Globe className="h-4 w-4 text-blue-600 shrink-0" />
              ) : (
                <MapPin className="h-4 w-4 text-blue-600 shrink-0" />
              )}
              <span>
                {isDefault ? (
                  <>
                    Viewing analytics for <strong>All India (National Overview)</strong>. Search your city in the top bar to focus analytics trends.
                  </>
                ) : (
                  <>
                    Analytics trends scoped to <strong>{currentLocation.name}</strong> (±55km area). Aggregations and charts filtered automatically.
                  </>
                )}
              </span>
            </div>
          </div>

          {/* Error Banner */}
          {isAnyError && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
              <span>
                Failed to load analytics data: {activeError instanceof Error ? activeError.message : 'Unknown error'}
              </span>
            </div>
          )}

          {/* Filters Bar (Always visible on desktop, toggleable on mobile) */}
          <div className={`${mobileFilterOpen ? 'block' : 'hidden md:block'}`}>
            <AnalyticsFilters
              filters={filters}
              tempFilters={tempFilters}
              onTempChange={setTempFilters}
              onApply={handleApplyFilters}
              onReset={handleResetFilters}
              isFetching={isSummaryFetching}
            />
          </div>

          {/* 1. KPI Cards (Migrated to dashboardApi.getSummary) */}
          <AnalyticsKpiCards
            summary={summaryData}
            timeRange={filters.timeRange}
            isLoading={isSummaryLoading}
          />

          {/* 2. Main Activity Chart (Migrated to analyticsApi.getTrends) */}
          <ReportActivityChart
            trendData={trendData}
            timeRange={filters.timeRange}
            isLoading={isTrendLoading}
          />

          {/* 3. 2-Column Grid: Event & Severity Distribution (Migrated to dashboardApi.getSummary) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <EventDistributionCard
              distribution={summaryData?.category_distribution}
              isLoading={isSummaryLoading}
            />
            <SeverityDistributionCard
              severity={summaryData?.severity}
              isLoading={isSummaryLoading}
            />
          </div>

          {/* 4. Recent Reports Table (Optimized single-page incidentApi.listIncidents query) */}
          <RecentReportsTable
            reports={recentIncidents}
            isLoading={isRecentLoading}
          />

          {/* 5. 2-Column Grid: Verification Status & Regional Activity (Migrated to analyticsApi.getRegional) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <VerificationStatusCard
              verification={summaryData?.verification}
              isLoading={isSummaryLoading}
            />
            <RegionalActivityCard
              regionalData={regionalData}
              isLoading={isRegionalLoading}
            />
          </div>

          {/* 6. Observed Patterns Banner (Migrated to dashboardApi.getSummary) */}
          <ObservedPatternsCard
            summary={summaryData}
            isLoading={isSummaryLoading}
          />
        </div>
      </main>

      <Footer />
      <MobileBottomNav />
    </div>
  );
};
