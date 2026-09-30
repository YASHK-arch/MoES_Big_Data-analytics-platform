import React, { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { MobileBottomNav } from '@/components/layout/MobileBottomNav';
import { QueueKpiCards } from '@/features/admin/QueueKpiCards';
import { QueueFilters, QueueFilterState } from '@/features/admin/QueueFilters';
import { QueueTable } from '@/features/admin/QueueTable';
import { QueueMobileList } from '@/features/admin/QueueMobileList';
import { ReviewReportDrawer } from '@/features/admin/ReviewReportDrawer';
import { fetchReportList } from '@/services/reportApi';
import { dashboardApi } from '@/services/dashboardApi';
import {
  DashboardSummaryQueryParams,
  ReportDetailData,
  ReportListQueryParams,
} from '@/types';
import { Link } from 'react-router-dom';
import { adminApi } from '@/services/adminApi';
import { incidentKeys, dashboardKeys, analyticsKeys } from '@/lib/queryKeys';
import {
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  Loader2,
  ShieldCheck,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

export const AdminVerificationQueuePage: React.FC = () => {
  const queryClient = useQueryClient();

  const [filters, setFilters] = useState<QueueFilterState>({
    status: 'ACTIVE',
    category: 'ALL',
    severity: 'ALL',
    searchQuery: '',
  });

  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [selectedReport, setSelectedReport] = useState<ReportDetailData | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const [isBulkLoading, setIsBulkLoading] = useState(false);
  const [bulkFeedback, setBulkFeedback] = useState<string | null>(null);

  // Map UI filters to backend query parameters
  const queryParams: ReportListQueryParams = useMemo(() => {
    const params: ReportListQueryParams = {
      page,
      page_size: pageSize,
    };

    if (filters.status === 'ACTIVE') {
      params.status = 'PENDING,UNDER_REVIEW';
    } else if (filters.status !== 'ALL') {
      params.status = filters.status;
    }

    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }

    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }

    return params;
  }, [filters.status, filters.category, filters.severity, page]);

  // Fetch report list from backend for table & mobile cards
  const { data: response, isLoading } = useQuery({
    queryKey: ['admin-queue-reports', queryParams],
    queryFn: () => fetchReportList(queryParams),
    staleTime: 1000 * 30, // 30 seconds
  });

  // Summary parameters for authoritative queue-wide KPI metrics
  const summaryParams: DashboardSummaryQueryParams = useMemo(() => {
    const params: DashboardSummaryQueryParams = {
      time_range: 'all',
    };

    if (filters.category !== 'ALL') {
      params.category = filters.category;
    }

    if (filters.severity !== 'ALL') {
      params.severity = filters.severity;
    }

    return params;
  }, [filters.category, filters.severity]);

  // Fetch server-side aggregated summary for Queue KPI cards
  const { data: summaryResponse, isLoading: isSummaryLoading } = useQuery({
    queryKey: dashboardKeys.summary(summaryParams as Record<string, unknown>),
    queryFn: ({ signal }) => dashboardApi.getSummary(summaryParams, signal),
    staleTime: 1000 * 30, // 30 seconds
  });

  // Client-side search filtering (by tracking_id, title, location)
  const filteredReports = useMemo(() => {
    const rawReports = response?.data || [];
    const query = filters.searchQuery.trim().toLowerCase();
    if (!query) return rawReports;

    return rawReports.filter((r) => {
      const matchTracking = r.tracking_id.toLowerCase().includes(query);
      const matchTitle = r.title.toLowerCase().includes(query);
      const matchLocation = r.location?.name?.toLowerCase().includes(query) ?? false;
      return matchTracking || matchTitle || matchLocation;
    });
  }, [response?.data, filters.searchQuery]);

  // Handle report selection for review
  const handleSelectReport = (report: ReportDetailData) => {
    setSelectedReport(report);
  };

  // Checkbox bulk selection helpers
  const handleToggleSelectId = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    if (selectedIds.size === filteredReports.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredReports.map((r) => r.id)));
    }
  };

  const handleResetFilters = () => {
    setFilters({
      status: 'ACTIVE',
      category: 'ALL',
      severity: 'ALL',
      searchQuery: '',
    });
    setPage(1);
  };

  const handleActionComplete = () => {
    // Invalidate prefix queries so all queue filters, lists, details, dashboard, and analytics refresh automatically
    queryClient.invalidateQueries({ queryKey: incidentKeys.verificationQueues() });
    queryClient.invalidateQueries({ queryKey: incidentKeys.lists() });
    queryClient.invalidateQueries({ queryKey: incidentKeys.geoAll() });
    queryClient.invalidateQueries({ queryKey: incidentKeys.details() });
    queryClient.invalidateQueries({ queryKey: dashboardKeys.all });
    queryClient.invalidateQueries({ queryKey: analyticsKeys.all });
    queryClient.invalidateQueries({ queryKey: ['admin-queue-reports'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-reports'] });
    queryClient.invalidateQueries({ queryKey: ['live-map-reports'] });
    queryClient.invalidateQueries({ queryKey: ['reports'] });
    setSelectedReport(null);
  };

  const handleExport = async (format: 'csv' | 'geojson') => {
    try {
      setIsExporting(format);
      await adminApi.downloadExport(format, {
        limit: 50000,
        category: filters.category !== 'ALL' ? filters.category : undefined,
        status:
          filters.status !== 'ALL'
            ? filters.status === 'ACTIVE'
              ? 'PENDING,UNDER_REVIEW'
              : filters.status
            : undefined,
        severity: filters.severity !== 'ALL' ? filters.severity : undefined,
      });
    } catch (err) {
      console.error(`Export ${format} failed:`, err);
    } finally {
      setIsExporting(null);
    }
  };

  const handleBulkAction = async (action: 'VERIFY' | 'REJECT') => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds).slice(0, 100);
    const confirmed = window.confirm(
      `Are you sure you want to bulk ${action.toLowerCase()} ${ids.length} selected report(s)?`
    );
    if (!confirmed) return;

    try {
      setIsBulkLoading(true);
      setBulkFeedback(null);
      const res = await adminApi.bulkVerification({
        incident_ids: ids,
        action,
        notes: `Bulk operator ${action.toLowerCase()} triage action`,
        rejection_reason: action === 'REJECT' ? 'OPERATOR_BULK_TRIAGE' : undefined,
      });
      setBulkFeedback(
        `Successfully ${action === 'VERIFY' ? 'verified' : 'rejected'} ${res.data.processed_count} incident(s).`
      );
      setSelectedIds(new Set());
      handleActionComplete();
      setTimeout(() => setBulkFeedback(null), 5000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Bulk action failed';
      setBulkFeedback(`Error: ${msg}`);
    } finally {
      setIsBulkLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Navbar />

      <main className="flex-1 pb-16 pt-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Header Banner */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
                  Verification Queue
                </h1>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                Review and triage incoming citizen reports requiring authorized operator attention.
              </p>
            </div>

            {/* Admin Header Actions */}
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to="/admin/audit-logs"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
              >
                <ClipboardList className="h-3.5 w-3.5 text-slate-500" />
                <span>Audit Logs</span>
              </Link>

              <button
                type="button"
                onClick={() => handleExport('csv')}
                disabled={isExporting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
              >
                {isExporting === 'csv' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5 text-slate-500" />
                )}
                <span>Export CSV</span>
              </button>

              <button
                type="button"
                onClick={() => handleExport('geojson')}
                disabled={isExporting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
              >
                {isExporting === 'geojson' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5 text-slate-500" />
                )}
                <span>Export GeoJSON</span>
              </button>
            </div>
          </div>

          {/* Feedback Banner */}
          {bulkFeedback && (
            <div
              className={`mt-4 p-3 rounded-xl border text-xs font-medium flex items-center justify-between ${
                bulkFeedback.startsWith('Error')
                  ? 'bg-rose-50 border-rose-200 text-rose-800'
                  : 'bg-emerald-50 border-emerald-200 text-emerald-800'
              }`}
            >
              <span>{bulkFeedback}</span>
              <button
                type="button"
                onClick={() => setBulkFeedback(null)}
                className="text-slate-400 hover:text-slate-600 font-bold ml-2"
              >
                ✕
              </button>
            </div>
          )}

          {/* Bulk Action Toolbar */}
          {selectedIds.size > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50/90 p-3 shadow-xs">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                  {selectedIds.size}
                </span>
                <span className="text-xs font-semibold text-blue-950">
                  {selectedIds.size} incident{selectedIds.size > 1 ? 's' : ''} selected
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs text-blue-700 hover:text-blue-900 underline ml-2 cursor-pointer"
                >
                  Clear
                </button>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={isBulkLoading}
                  onClick={() => handleBulkAction('VERIFY')}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isBulkLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  )}
                  <span>Verify Selected ({selectedIds.size})</span>
                </button>

                <button
                  type="button"
                  disabled={isBulkLoading}
                  onClick={() => handleBulkAction('REJECT')}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isBulkLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" />
                  )}
                  <span>Reject Selected ({selectedIds.size})</span>
                </button>
              </div>
            </div>
          )}

          {/* KPI Summary Cards */}
          <div className="mt-6">
            <QueueKpiCards
              summary={summaryResponse?.data}
              isLoading={isSummaryLoading}
            />
          </div>

          {/* Filters Bar */}
          <div className="mt-6">
            <QueueFilters
              filters={filters}
              onChange={(newFilters) => {
                setFilters(newFilters);
                setPage(1);
              }}
              onReset={handleResetFilters}
            />
          </div>

          {/* Queue Content Area: Table / List & Review Panel */}
          <div className="mt-6 flex flex-col lg:flex-row gap-6 items-start">
            {/* Left Main: Review Table (Desktop) / Cards (Mobile) */}
            <div className={`w-full transition-all duration-300 ${selectedReport ? 'lg:w-7/12 xl:w-2/3' : 'lg:w-full'}`}>
              {/* Desktop Table View */}
              <div className="hidden md:block">
                <QueueTable
                  reports={filteredReports}
                  selectedReport={selectedReport}
                  onSelectReport={handleSelectReport}
                  selectedIds={selectedIds}
                  onToggleSelectId={handleToggleSelectId}
                  onToggleSelectAll={handleToggleSelectAll}
                  isLoading={isLoading}
                />
              </div>

              {/* Mobile Card List View */}
              <div className="block md:hidden">
                <QueueMobileList
                  reports={filteredReports}
                  selectedReport={selectedReport}
                  onSelectReport={handleSelectReport}
                  isLoading={isLoading}
                />
              </div>

              {/* Pagination Controls */}
              {response?.pagination && response.pagination.total_pages > 1 && (
                <div className="mt-4 flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                  <div className="text-xs text-slate-600">
                    Page <span className="font-bold text-slate-900">{page}</span> of{' '}
                    <span className="font-bold text-slate-900">{response.pagination.total_pages}</span> (
                    {response.pagination.total_records} total reports)
                  </div>

                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      disabled={!response.pagination.has_prev}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="flex items-center space-x-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                      <span>Previous</span>
                    </button>
                    <button
                      type="button"
                      disabled={!response.pagination.has_next}
                      onClick={() => setPage((p) => p + 1)}
                      className="flex items-center space-x-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <span>Next</span>
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Right Drawer / Review Panel (Desktop) */}
            {selectedReport && (
              <div className="hidden lg:block lg:w-5/12 xl:w-1/3 sticky top-6 rounded-2xl border border-slate-200 bg-white shadow-md overflow-hidden h-[calc(100vh-5rem)] flex flex-col">
                <ReviewReportDrawer
                  report={selectedReport}
                  onClose={() => setSelectedReport(null)}
                  onActionComplete={handleActionComplete}
                />
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Mobile Bottom Sheet / Modal Review Panel */}
      {selectedReport && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/60 backdrop-blur-xs lg:hidden">
          <div className="h-[88vh] w-full rounded-t-3xl bg-white shadow-2xl overflow-hidden flex flex-col animate-in slide-in-from-bottom duration-200">
            <ReviewReportDrawer
              report={selectedReport}
              onClose={() => setSelectedReport(null)}
              onActionComplete={handleActionComplete}
            />
          </div>
        </div>
      )}

      <Footer />
      <MobileBottomNav />
    </div>
  );
};
