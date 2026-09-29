import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { MobileBottomNav } from '@/components/layout/MobileBottomNav';
import {
  DashboardFilters,
  DashboardFilterState,
} from '@/features/dashboard/DashboardFilters';
import { REGIONS } from '@/features/dashboard/constants';
import { DashboardKpiCards } from '@/features/dashboard/DashboardKpiCards';
import { DashboardMap } from '@/features/dashboard/DashboardMap';
import { RecentIncidentFeed } from '@/features/dashboard/RecentIncidentFeed';
import { IncidentTrendCard } from '@/features/dashboard/IncidentTrendCard';
import { EventDistributionCard } from '@/features/dashboard/EventDistributionCard';
import { VerificationSummaryCard } from '@/features/dashboard/VerificationSummaryCard';
import { dashboardApi } from '@/services/dashboardApi';
import { incidentApi } from '@/services/incidentApi';
import { dashboardKeys, incidentKeys } from '@/lib/queryKeys';
import { geoJSONToMapPoints, MapIncidentPoint } from '@/features/map/adapters';
import {
  DashboardSummaryQueryParams,
  IncidentListQueryParams,
  IncidentSummary,
  ReportDetailData,
} from '@/types';
import { useLocationScope } from '@/hooks';
import { AlertTriangle, MapPin, Globe } from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const { currentLocation, isDefault } = useLocationScope();

  const [filters, setFilters] = useState<DashboardFilterState>({
    timeRange: '24h',
    hazard: 'ALL',
    region: 'ALL',
    status: 'ALL',
  });

  const [selectedReport, setSelectedReport] = useState<MapIncidentPoint | null>(null);

  // Compute effective bounding box: manual region filter takes precedence; otherwise use detected/searched city bbox
  const effectiveBbox = useMemo(() => {
    const regionInfo = REGIONS[filters.region];
    if (regionInfo?.bbox) {
      return regionInfo.bbox;
    }
    return currentLocation.bbox || undefined;
  }, [filters.region, currentLocation.bbox]);

  // Summary aggregation query parameters
  const summaryParams: DashboardSummaryQueryParams = useMemo(() => {
    const params: DashboardSummaryQueryParams = {};
    if (filters.timeRange) {
      params.time_range = filters.timeRange;
    }
    if (filters.hazard !== 'ALL') {
      params.category = filters.hazard;
    }
    if (filters.status !== 'ALL') {
      params.status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }
    return params;
  }, [filters, effectiveBbox]);

  // Fetch SQL-aggregated summary data from backend
  const {
    data: summaryResponse,
    isLoading: isSummaryLoading,
    isFetching: isSummaryFetching,
    isError: isSummaryError,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: dashboardKeys.summary(summaryParams as Record<string, unknown>),
    queryFn: ({ signal }) => dashboardApi.getSummary(summaryParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const summaryData = summaryResponse?.data;

  // Compute hours_ago for GeoJSON map query
  const geoHoursAgo = useMemo(() => {
    if (filters.timeRange === '24h') return 24;
    if (filters.timeRange === '48h') return 48;
    if (filters.timeRange === '7d') return 168;
    return undefined; // All-time
  }, [filters.timeRange]);

  const geoParams = useMemo(() => {
    const p: { status?: string; category?: string; hours_ago?: number } = {};
    if (filters.hazard !== 'ALL') p.category = filters.hazard;
    if (filters.status !== 'ALL') p.status = filters.status;
    if (geoHoursAgo) p.hours_ago = geoHoursAgo;
    return p;
  }, [filters.hazard, filters.status, geoHoursAgo]);

  // Fetch GeoJSON FeatureCollection for situational map markers (single bounded request)
  const {
    data: geoResponse,
    isFetching: isGeoFetching,
    isError: isGeoError,
    error: geoError,
    refetch: refetchGeo,
  } = useQuery({
    queryKey: incidentKeys.geo(effectiveBbox || '', geoParams as Record<string, unknown>),
    queryFn: ({ signal }) => incidentApi.getGeoIncidents(effectiveBbox, geoParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const mapPoints = useMemo(() => geoJSONToMapPoints(geoResponse), [geoResponse]);

  // Compute from_date based on timeRange filter for bounded incident feed
  const fromDate = useMemo(() => {
    const now = Date.now();
    if (filters.timeRange === '24h') {
      return new Date(now - 24 * 60 * 60 * 1000).toISOString();
    }
    if (filters.timeRange === '48h') {
      return new Date(now - 48 * 60 * 60 * 1000).toISOString();
    }
    if (filters.timeRange === '7d') {
      return new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();
    }
    return undefined;
  }, [filters.timeRange]);

  // Query parameters for bounded recent incidents feed (page_size: 6, sorted by occurred_at DESC)
  const recentFeedParams: IncidentListQueryParams = useMemo(() => {
    const params: IncidentListQueryParams = {
      page: 1,
      page_size: 6,
      sort_by: 'occurred_at',
      sort_order: 'desc',
    };

    if (fromDate) {
      params.from_date = fromDate;
    }
    if (filters.hazard !== 'ALL') {
      params.category = filters.hazard;
    }
    if (filters.status !== 'ALL') {
      params.verification_status = filters.status;
    }
    if (effectiveBbox) {
      params.bbox = effectiveBbox;
    }

    return params;
  }, [filters, fromDate, effectiveBbox]);

  // Fetch bounded recent incidents for feed
  const {
    data: recentFeedResponse,
    isLoading: isRecentLoading,
    isFetching: isRecentFetching,
    isError: isRecentError,
    error: recentError,
    refetch: refetchRecent,
  } = useQuery({
    queryKey: incidentKeys.list(recentFeedParams as Record<string, unknown>),
    queryFn: ({ signal }) => incidentApi.listIncidents(recentFeedParams, signal),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });

  const recentIncidents = useMemo(
    () => recentFeedResponse?.data || [],
    [recentFeedResponse]
  );

  const targetRegion = useMemo(() => {
    const reg = REGIONS[filters.region];
    if (reg && filters.region !== 'ALL') {
      return { center: reg.center, zoom: reg.zoom };
    }
    if (currentLocation.lat != null && currentLocation.lon != null && !isDefault) {
      return { center: [currentLocation.lat, currentLocation.lon] as [number, number], zoom: 10 };
    }
    return reg ? { center: reg.center, zoom: reg.zoom } : undefined;
  }, [filters.region, currentLocation, isDefault]);

  const handleRefresh = () => {
    refetchSummary();
    refetchGeo();
    refetchRecent();
  };

  const handleSelectFeedReport = (rep: IncidentSummary | ReportDetailData) => {
    const match = mapPoints.find((p) => p.tracking_id === rep.tracking_id);
    if (match) {
      setSelectedReport(match);
    } else if (rep.location?.latitude != null && rep.location?.longitude != null) {
      const rawSev = (rep as { severity?: string | { level?: string } }).severity;
      const sevStr = typeof rawSev === 'string' ? rawSev : rawSev?.level || 'MODERATE';
      setSelectedReport({
        id: rep.id,
        tracking_id: rep.tracking_id,
        title: rep.title,
        severity: sevStr,
        verification_status:
          typeof rep.verification_status === 'string' ? rep.verification_status : 'PENDING',
        occurred_at: rep.occurred_at || null,
        location: {
          latitude: rep.location.latitude,
          longitude: rep.location.longitude,
          name: rep.location.name,
        },
      });
    }
  };

  const isFetching = isSummaryFetching || isGeoFetching || isRecentFetching;
  const isError = isSummaryError || isGeoError || isRecentError;
  const activeError = summaryError || geoError || recentError;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50/60 text-slate-900 pb-16 md:pb-0">
      {/* Top Navbar */}
      <Navbar />

      {/* Main Dashboard Workspace */}
      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
          {/* Top Filter Bar */}
          <DashboardFilters
            filters={filters}
            onChange={setFilters}
            onRefresh={handleRefresh}
            isFetching={isFetching}
          />

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
                    Viewing <strong>All India (National Overview)</strong>. Search your city in the top bar to narrow telemetry.
                  </>
                ) : (
                  <>
                    Situational view scoped to <strong>{currentLocation.name}</strong> (±55km radius). Telemetry, maps, and KPIs filtered automatically.
                  </>
                )}
              </span>
            </div>
          </div>

          {/* Error Banner if API call fails */}
          {isError && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs text-red-700 flex items-center space-x-2">
              <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
              <span>
                Failed to load situational dashboard data:{' '}
                {activeError instanceof Error ? activeError.message : 'Unknown error'}.
              </span>
            </div>
          )}

          {/* Row 1: KPI Summary Cards (Server-side Aggregated) */}
          <DashboardKpiCards
            summary={summaryData}
            isLoading={isSummaryLoading}
          />

          {/* Row 2: Situational Overview Map + Live Incident Feed (GeoJSON Map & Bounded Feed) */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Left 8 columns: Situational Map */}
            <div className="lg:col-span-8">
              <DashboardMap
                reports={mapPoints}
                severeCount={summaryData?.severity?.severe_high_count}
                selectedReport={selectedReport}
                onSelectReport={setSelectedReport}
                targetRegion={targetRegion}
              />
            </div>

            {/* Right 4 columns: Recent Incident Feed */}
            <div className="lg:col-span-4">
              <RecentIncidentFeed
                reports={recentIncidents}
                totalCount={summaryData?.total_count ?? recentFeedResponse?.pagination?.total_records}
                selectedReport={selectedReport}
                onSelectReport={handleSelectFeedReport}
                isLoading={isRecentLoading}
              />
            </div>
          </div>

          {/* Row 3: Bottom Analytics and Distribution Cards (Server-side Aggregated) */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            <IncidentTrendCard
              distribution={summaryData?.diurnal_distribution}
              isLoading={isSummaryLoading}
            />
            <EventDistributionCard
              distribution={summaryData?.category_distribution}
              isLoading={isSummaryLoading}
            />
            <VerificationSummaryCard
              verification={summaryData?.verification}
              totalCount={summaryData?.total_count}
              isLoading={isSummaryLoading}
            />
          </div>
        </div>
      </main>

      {/* Footer */}
      <Footer />

      {/* Mobile Bottom Navigation */}
      <MobileBottomNav />
    </div>
  );
};
