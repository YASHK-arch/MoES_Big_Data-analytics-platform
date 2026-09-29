// End-to-End Realtime Integration Test Suite (Frontend)

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { RealtimeService } from '../services/realtimeService';
import { incidentKeys, dashboardKeys, analyticsKeys } from '../lib/queryKeys';
import { RealtimeEvent } from '../types/realtime';

// Mock EventSource implementation for deterministic SSE simulation
class MockEventSourceIntegration {
  public static instances: MockEventSourceIntegration[] = [];
  public url: string;
  public options?: EventSourceInit;
  public readyState: number = 0; // CONNECTING
  public onopen: ((event: Event) => void) | null = null;
  public onerror: ((event: Event) => void) | null = null;
  public onmessage: ((event: MessageEvent) => void) | null = null;
  private listeners: Map<string, Array<(event: MessageEvent) => void>> = new Map();

  constructor(url: string, options?: EventSourceInit) {
    this.url = url;
    this.options = options;
    MockEventSourceIntegration.instances.push(this);
  }

  public addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    const list = this.listeners.get(type) || [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  public removeEventListener(type: string, listener: (event: MessageEvent) => void): void {
    const list = this.listeners.get(type) || [];
    this.listeners.set(
      type,
      list.filter((l) => l !== listener)
    );
  }

  public close(): void {
    this.readyState = 2; // CLOSED
  }

  public emitOpen(): void {
    this.readyState = 1; // OPEN
    if (this.onopen) {
      this.onopen(new Event('open'));
    }
  }

  public emitError(): void {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }

  public emitEvent(type: string, data: string): void {
    const event = new MessageEvent(type, { data });
    const list = this.listeners.get(type) || [];
    list.forEach((listener) => listener(event));
    if (type === 'message' && this.onmessage) {
      this.onmessage(event);
    }
  }
}

describe('End-to-End Realtime Integration & Cache Invalidation', () => {
  let service: RealtimeService;
  let queryClient: QueryClient;
  let invalidateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    MockEventSourceIntegration.instances = [];
    (globalThis as unknown as { EventSource: typeof MockEventSourceIntegration }).EventSource =
      MockEventSourceIntegration;
    (global as unknown as { EventSource: typeof MockEventSourceIntegration }).EventSource =
      MockEventSourceIntegration;
    if (typeof window !== 'undefined') {
      (window as unknown as { EventSource: typeof MockEventSourceIntegration }).EventSource =
        MockEventSourceIntegration;
    }

    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 1000 * 60 * 5,
          retry: false,
        },
      },
    });
    invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    service = new RealtimeService();
    service.debounceIntervalMs = 0;
  });

  afterEach(() => {
    service.destroy();
    vi.restoreAllMocks();
  });

  describe('1. Citizen Report Ingestion -> Realtime Notification -> Query Freshness', () => {
    it('report.created event triggers query invalidation and marks active caches stale', async () => {
      // 1. Seed query cache with active incident list
      const listKey = incidentKeys.lists();
      await queryClient.prefetchQuery({
        queryKey: listKey,
        queryFn: () => [{ id: 'existing-1', title: 'Initial Incident' }],
      });

      // Assert initially fresh
      const stateBefore = queryClient.getQueryState(listKey);
      expect(stateBefore?.isInvalidated).toBe(false);

      // 2. Initialize RealtimeService and connect
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      // 3. Backend emits report.created SSE event
      const ssePayload = JSON.stringify({
        event_id: 'e2e-rep-created-uuid-001',
        event_type: 'report.created',
        occurred_at: '2026-08-30T12:00:00Z',
        entity_id: 'rep-e2e-1',
        tracking_id: 'RPT-E2E-001',
        payload: {
          category_code: 'FLOOD_WATERLOGGING',
          severity: 'HIGH',
          verification_status: 'PENDING',
          location_name: 'Kurla West',
          latitude: 19.065,
          longitude: 72.879,
          occurred_at: '2026-08-30T12:00:00Z',
        },
      });

      mockSSE.emitEvent('report.created', ssePayload);

      // 4. Verify exact invalidation keys
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.geoAll() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.verificationQueues() });

      // 5. Query state is now invalidated / marked for refetch
      const stateAfter = queryClient.getQueryState(listKey);
      expect(stateAfter?.isInvalidated).toBe(true);
    });
  });

  describe('2. Verification Transition -> Granular Incident Detail & Queue Invalidation', () => {
    it('report.verification_changed invalidates specific incident detail and verification queue', async () => {
      const detailKey = incidentKeys.detail('rep-e2e-2');
      await queryClient.prefetchQuery({
        queryKey: detailKey,
        queryFn: () => ({ id: 'rep-e2e-2', verification_status: 'PENDING' }),
      });

      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const ssePayload = JSON.stringify({
        event_id: 'e2e-rep-verify-uuid-002',
        event_type: 'report.verification_changed',
        occurred_at: '2026-08-30T12:05:00Z',
        entity_id: 'rep-e2e-2',
        tracking_id: 'RPT-E2E-002',
        payload: {
          category_code: 'HEAVY_RAINFALL',
          previous_status: 'PENDING',
          new_status: 'VERIFIED',
          reason: 'Corroborated by radar',
          verified_at: '2026-08-30T12:05:00Z',
        },
      });

      mockSSE.emitEvent('report.verification_changed', ssePayload);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail('rep-e2e-2') });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.verificationQueues() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });

      const detailState = queryClient.getQueryState(detailKey);
      expect(detailState?.isInvalidated).toBe(true);
    });
  });

  describe('3. Intelligence Completion & Cluster Updates', () => {
    it('report.intelligence_ready invalidates intelligence and detail caches', () => {
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const ssePayload = JSON.stringify({
        event_id: 'e2e-intel-uuid-003',
        event_type: 'report.intelligence_ready',
        occurred_at: '2026-08-30T12:10:00Z',
        entity_id: 'rep-e2e-3',
        tracking_id: 'RPT-E2E-003',
        payload: {
          credibility_score: 0.92,
          readiness: 'INTELLIGENCE_READY',
          corroborated: true,
        },
      });

      mockSSE.emitEvent('report.intelligence_ready', ssePayload);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail('rep-e2e-3') });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
    });

    it('cluster.updated invalidates geospatial and dashboard aggregates', () => {
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const ssePayload = JSON.stringify({
        event_id: 'e2e-cluster-uuid-004',
        event_type: 'cluster.updated',
        occurred_at: '2026-08-30T12:15:00Z',
        entity_id: 'clus-e2e-1',
        payload: {
          cluster_id: 'clus-e2e-1',
          member_count: 8,
          primary_report_id: 'rep-e2e-1',
          centroid_latitude: 19.07,
          centroid_longitude: 72.88,
        },
      });

      mockSSE.emitEvent('cluster.updated', ssePayload);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.geoAll() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
    });
  });

  describe('4. Reconnect, Stream Replay & Deduplication Isolation', () => {
    it('suppresses duplicate invalidation when replayed event arrives with same event_id', () => {
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const payload = JSON.stringify({
        event_id: 'stable-outbox-uuid-777',
        event_type: 'report.created',
        occurred_at: '2026-08-30T12:20:00Z',
        entity_id: 'rep-777',
        payload: {},
      });

      // 1. Initial live delivery
      mockSSE.emitEvent('report.created', payload);
      expect(invalidateSpy).toHaveBeenCalledTimes(5);

      // 2. Simulated disconnect and reconnect replay with same event_id
      mockSSE.emitError();
      mockSSE.emitEvent('report.created', payload);

      // Invalidation count must not increase (deduplication success)
      expect(invalidateSpy).toHaveBeenCalledTimes(5);
    });
  });

  describe('5. System Resync Required Flow', () => {
    it('system.resync_required triggers broad authoritative REST query reconciliation', () => {
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const resyncPayload = JSON.stringify({
        event_id: 'system-resync-uuid',
        event_type: 'system.resync_required',
        occurred_at: '2026-08-30T12:25:00Z',
        entity_id: 'system',
        payload: {
          reason: 'RESYNC_REQUIRED',
          message: 'Stream history pruned. Client must refresh authoritative state via REST API.',
        },
      });

      mockSSE.emitEvent('system.resync_required', resyncPayload);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
    });
  });

  describe('6. Multiple Frontend Subscribers on Shared Singleton', () => {
    it('dispatches to multiple subscriber callbacks without duplicating EventSource sockets', () => {
      service.initialize(queryClient);
      const mockSSE = MockEventSourceIntegration.instances[0];
      mockSSE.emitOpen();

      const received1: RealtimeEvent[] = [];
      const received2: RealtimeEvent[] = [];

      service.subscribe((evt) => received1.push(evt));
      service.subscribe((evt) => received2.push(evt));

      const eventPayload = JSON.stringify({
        event_id: 'multi-sub-uuid-1',
        event_type: 'report.created',
        occurred_at: '2026-08-30T12:30:00Z',
        entity_id: 'rep-multi-1',
        payload: {},
      });

      mockSSE.emitEvent('report.created', eventPayload);

      expect(received1.length).toBe(1);
      expect(received2.length).toBe(1);
      expect(received1[0].event_id).toBe('multi-sub-uuid-1');
      expect(received2[0].event_id).toBe('multi-sub-uuid-1');

      // Exactly 1 EventSource connection was instantiated
      expect(MockEventSourceIntegration.instances.length).toBe(1);
    });
  });
});
