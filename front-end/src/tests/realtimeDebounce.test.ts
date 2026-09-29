import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { RealtimeService } from '../services/realtimeService';
import { incidentKeys, dashboardKeys } from '../lib/queryKeys';
import type { RealtimeEvent } from '../types/realtime';

describe('RealtimeService Query Invalidation Debouncing (P6)', () => {
  let service: RealtimeService;
  let queryClient: QueryClient;
  let invalidateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    queryClient = new QueryClient();
    invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    service = new RealtimeService();
    // Default 2000ms debounce interval
    service.debounceIntervalMs = 2000;
    service.initialize(queryClient);
  });

  afterEach(() => {
    service.destroy();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('debounces rapid burst of events to a single invalidation per query group at 2 seconds trailing edge', () => {
    const event: RealtimeEvent = {
      event_id: 'evt-1',
      event_type: 'report.created',
      occurred_at: new Date().toISOString(),
      entity_id: 'rep-1',
      tracking_id: 'TRK-1',
      payload: {},
    };

    // Burst of 10 events within 500ms
    for (let i = 0; i < 10; i++) {
      service.invalidateQueriesForEvent({ ...event, event_id: `evt-${i}` });
      vi.advanceTimersByTime(50);
    }

    // Invalidation has NOT fired yet (still within 2000ms trailing debounce)
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: dashboardKeys.all });

    // Advance 1900ms (total elapsed since last event: 1900ms < 2000ms)
    vi.advanceTimersByTime(1900);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });

    // Advance remaining 200ms -> 2000ms past the last event
    vi.advanceTimersByTime(200);

    // Lists and dashboard are now invalidated exactly ONCE each (not 10 times)
    const listCalls = invalidateSpy.mock.calls.filter(
      (call) => JSON.stringify(call[0]?.queryKey) === JSON.stringify(incidentKeys.lists())
    );
    expect(listCalls.length).toBe(1);

    const dashboardCalls = invalidateSpy.mock.calls.filter(
      (call) => JSON.stringify(call[0]?.queryKey) === JSON.stringify(dashboardKeys.all)
    );
    expect(dashboardCalls.length).toBe(1);
  });

  it('immediately invalidates currently open incident detail while debouncing group queries', () => {
    const activeId = 'rep-open-current';
    service.setActiveIncidentId(activeId);

    const event: RealtimeEvent = {
      event_id: 'evt-verify-immediate',
      event_type: 'report.verification_changed',
      occurred_at: new Date().toISOString(),
      entity_id: activeId,
      tracking_id: 'TRK-999',
      payload: { new_status: 'VERIFIED' },
    };

    service.invalidateQueriesForEvent(event);

    // Detail query for currently open incident is invalidated IMMEDIATELY (0ms delay)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail(activeId) });

    // Group queries (lists, dashboard) remain pending in the 2s debounce window
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: dashboardKeys.all });

    // After 2000ms, group queries fire
    vi.advanceTimersByTime(2000);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
  });

  it('debounces detail invalidation for incidents that are NOT currently open', () => {
    service.setActiveIncidentId('rep-open-current');

    const backgroundId = 'rep-background-404';
    const event: RealtimeEvent = {
      event_id: 'evt-verify-bg',
      event_type: 'report.verification_changed',
      occurred_at: new Date().toISOString(),
      entity_id: backgroundId,
      tracking_id: 'TRK-404',
      payload: { new_status: 'VERIFIED' },
    };

    service.invalidateQueriesForEvent(event);

    // Background incident detail is NOT called immediately
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: incidentKeys.detail(backgroundId) });

    // After 2000ms trailing debounce, it fires
    vi.advanceTimersByTime(2000);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail(backgroundId) });
  });
});
