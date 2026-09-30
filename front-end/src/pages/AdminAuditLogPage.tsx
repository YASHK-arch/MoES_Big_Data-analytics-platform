import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { MobileBottomNav } from '@/components/layout/MobileBottomNav';
import { adminApi } from '@/services/adminApi';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Filter,
  RefreshCw,
  User,
} from 'lucide-react';

export const AdminAuditLogPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [actionFilter, setActionFilter] = useState('');

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin-audit-logs', { page, pageSize, action: actionFilter }],
    queryFn: () =>
      adminApi.getAuditLogs({
        page,
        page_size: pageSize,
        action: actionFilter || undefined,
      }),
    staleTime: 1000 * 30,
  });

  const logs = data?.data || [];
  const pagination = data?.pagination;

  const getActionBadge = (action: string) => {
    const actUpper = action.toUpperCase();
    if (actUpper.includes('VERIFY')) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
          {action}
        </span>
      );
    }
    if (actUpper.includes('REJECT')) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">
          {action}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-300">
        {action}
      </span>
    );
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Navbar />

      <main className="flex-1 pb-16 pt-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2">
                <Link
                  to="/admin/queue"
                  className="inline-flex items-center justify-center h-8 w-8 rounded-lg bg-slate-200 text-slate-700 hover:bg-slate-300 transition-colors"
                  title="Back to Verification Queue"
                >
                  <ArrowLeft className="h-4 w-4" />
                </Link>
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-800 text-white shadow-sm">
                  <ClipboardList className="h-4 w-4" />
                </div>
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
                  Operator Audit Logs
                </h1>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                Immutable chronological trail of operator verification actions, bulk decisions, and triage operations.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <Filter className="h-4 w-4 text-slate-500" />
              <label htmlFor="action-filter" className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                Action Filter:
              </label>
              <select
                id="action-filter"
                value={actionFilter}
                onChange={(e) => {
                  setActionFilter(e.target.value);
                  setPage(1);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All Actions</option>
                <option value="BULK_VERIFY">BULK_VERIFY</option>
                <option value="BULK_REJECT">BULK_REJECT</option>
                <option value="VERIFY">VERIFY</option>
                <option value="REJECT">REJECT</option>
              </select>
            </div>

            <div className="text-xs text-slate-500">
              Total Records:{' '}
              <span className="font-semibold text-slate-800">
                {pagination ? pagination.total_records : '...'}
              </span>
            </div>
          </div>

          {/* Audit Logs Table */}
          <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-3">Timestamp (UTC)</th>
                    <th scope="col" className="px-4 py-3">Action</th>
                    <th scope="col" className="px-4 py-3">Operator</th>
                    <th scope="col" className="px-4 py-3">Entity</th>
                    <th scope="col" className="px-4 py-3">Details / Payload</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {isLoading ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-slate-500">
                        <div className="flex items-center justify-center gap-2">
                          <RefreshCw className="h-4 w-4 animate-spin text-blue-600" />
                          <span>Loading audit records...</span>
                        </div>
                      </td>
                    </tr>
                  ) : logs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-slate-500">
                        No audit log records found matching the filter criteria.
                      </td>
                    </tr>
                  ) : (
                    logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                          {new Date(log.created_at).toLocaleString('en-IN', {
                            timeZone: 'UTC',
                            dateStyle: 'short',
                            timeStyle: 'medium',
                          })}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          {getActionBadge(log.action)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-700">
                          <div className="flex items-center gap-1.5">
                            <User className="h-3.5 w-3.5 text-slate-400" />
                            <span>{log.user_email || 'System Default'}</span>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs font-mono text-slate-600">
                          <div>
                            <span className="text-[10px] font-bold text-slate-400 block">{log.entity_type}</span>
                            <span className="truncate max-w-[140px] inline-block">{log.entity_id || '—'}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-700">
                          {log.payload ? (
                            <div className="max-w-md truncate">
                              {log.payload.tracking_id ? (
                                <span className="font-semibold text-slate-900 mr-2">
                                  [{String(log.payload.tracking_id)}]
                                </span>
                              ) : null}
                              {log.payload.notes ? (
                                <span className="italic text-slate-600">"{String(log.payload.notes)}"</span>
                              ) : log.payload.rejection_reason ? (
                                <span className="text-rose-600 font-medium">Reason: {String(log.payload.rejection_reason)}</span>
                              ) : (
                                <span className="font-mono text-slate-500 text-[11px]">{JSON.stringify(log.payload)}</span>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {pagination && pagination.total_pages > 1 && (
              <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3 sm:px-6">
                <div className="text-xs text-slate-600">
                  Showing page <span className="font-semibold text-slate-900">{page}</span> of{' '}
                  <span className="font-semibold text-slate-900">{pagination.total_pages}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={!pagination.has_prev}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(pagination.total_pages, p + 1))}
                    disabled={!pagination.has_next}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                  >
                    Next
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      <Footer />
      <MobileBottomNav />
    </div>
  );
};
