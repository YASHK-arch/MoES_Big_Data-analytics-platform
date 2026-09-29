// Realtime Service & SSE Event Manager Comprehensive Test Suite

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { RealtimeService, MAX_DEDUPE_SIZE } from '../services/realtimeService';
import { incidentKeys, dashboardKeys, analyticsKeys } from '../lib/queryKeys';
import { RealtimeEvent, RealtimeConnectionState } from '../types/realtime';

// Mock EventSource implementation
class MockEventSource {
  public static instances: MockEventSource[] = [];
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
    MockEventSource.instances.push(this);
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

describe('RealtimeService & Centralized SSE Manager', () => {
  let service: RealtimeService;
  let queryClient: QueryClient;
  let invalidateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    MockEventSource.instances = [];
    (globalThis as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    (global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    if (typeof window !== 'undefined') {
      (window as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    }

    queryClient = new QueryClient();
    invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    service = new RealtimeService();
    service.debounceIntervalMs = 0;
  });

  afterEach(() => {
    service.destroy();
    vi.restoreAllMocks();
  });

  describe('1. Connection Lifecycle & Singleton Behavior', () => {
    it('initializes and creates a single EventSource connection', () => {
      service.initialize(queryClient);
      expect(MockEventSource.instances.length).toBe(1);
      expect(MockEventSource.instances[0].url).toContain('/events/stream');
      expect(service.getState()).toBe('connecting');
    });

    it('updates state to open on SSE open event', () => {
      const states: RealtimeConnectionState[] = [];
      service.subscribeState((state) => states.push(state));

      service.initialize(queryClient);
      MockEventSource.instances[0].emitOpen();

      expect(service.getState()).toBe('open');
      expect(states).toContain('open');
    });

    it('does not create duplicate sockets if initialize/connect is called repeatedly', () => {
      service.initialize(queryClient);
      service.initialize(queryClient);
      service.connect();
      expect(MockEventSource.instances.length).toBe(1);
    });

    it('disconnect closes the underlying EventSource and updates state to closed', () => {
      service.initialize(queryClient);
      const mockInstance = MockEventSource.instances[0];
      mockInstance.emitOpen();

      service.disconnect();
      expect(service.getState()).toBe('closed');
      expect(mockInstance.readyState).toBe(2); // CLOSED
    });

    it('handles SSE error event without destroying singleton', () => {
      service.initialize(queryClient);
      const mockInstance = MockEventSource.instances[0];
      mockInstance.emitOpen();

      mockInstance.emitError();
      expect(service.getState()).toBe('error');
    });
  });

  describe('2. Event Parsing & Safe Envelope Validation', () => {
    it('parses valid canonical RealtimeEvent and dispatches to subscribers', () => {
      service.initialize(queryClient);
      const events: RealtimeEvent[] = [];
      service.subscribe((evt) => events.push(evt));

      const rawEvent = {
        event_id: 'evt-12345',
        event_type: 'report.created',
        occurred_at: '2026-08-30T12:00:00Z',
        entity_id: 'rep-001',
        tracking_id: 'RPT-2026-001',
        payload: {
          category_code: 'FLOOD_WATERLOGGING',
          severity: 'HIGH',
        },
      };

      MockEventSource.instances[0].emitEvent('report.created', JSON.stringify(rawEvent));

      expect(events.length).toBe(1);
      expect(events[0].event_id).toBe('evt-12345');
      expect(events[0].event_type).toBe('report.created');
      expect(events[0].entity_id).toBe('rep-001');
      expect(events[0].tracking_id).toBe('RPT-2026-001');
      expect((events[0].payload as Record<string, unknown>).category_code).toBe('FLOOD_WATERLOGGING');
    });

    it('safely ignores malformed JSON without crashing or invalidating queries', () => {
      service.initialize(queryClient);
      const events: RealtimeEvent[] = [];
      service.subscribe((evt) => events.push(evt));

      MockEventSource.instances[0].emitEvent('report.created', 'not-valid-json{{{');

      expect(events.length).toBe(0);
      expect(invalidateSpy).not.toHaveBeenCalled();
    });

    it('safely ignores payloads missing event_id', () => {
      service.initialize(queryClient);
      const events: RealtimeEvent[] = [];
      service.subscribe((evt) => events.push(evt));

      MockEventSource.instances[0].emitEvent(
        'report.created',
        JSON.stringify({ entity_id: 'rep-001', payload: {} })
      );

      expect(events.length).toBe(0);
      expect(invalidateSpy).not.toHaveBeenCalled();
    });
  });

  describe('3. Stable event_id Deduplication & Memory Bounds', () => {
    it('deduplicates duplicate events carrying the same event_id', () => {
      service.initialize(queryClient);
      const events: RealtimeEvent[] = [];
      service.subscribe((evt) => events.push(evt));

      const eventPayload = JSON.stringify({
        event_id: 'stable-uuid-999',
        event_type: 'report.created',
        occurred_at: '2026-08-30T12:00:00Z',
        entity_id: 'rep-999',
        payload: {},
      });

      // Emit twice (simulating at-least-once retry delivery)
      MockEventSource.instances[0].emitEvent('report.created', eventPayload);
      MockEventSource.instances[0].emitEvent('report.created', eventPayload);

      expect(events.length).toBe(1);
      // Invalidation called only once
      expect(invalidateSpy).toHaveBeenCalledTimes(5); // 5 queries for report.created
    });

    it('enforces bounded memory for deduplication queue (MAX_DEDUPE_SIZE)', () => {
      service.initialize(queryClient);

      // Fill beyond MAX_DEDUPE_SIZE
      for (let i = 0; i < MAX_DEDUPE_SIZE + 50; i++) {
        service.handleIncomingEvent(
          'report.created',
          JSON.stringify({
            event_id: `evt-${i}`,
            event_type: 'report.created',
            entity_id: `rep-${i}`,
            payload: {},
          })
        );
      }

      // Oldest event (evt-0) should have been evicted and can be processed again
      const replayedOldest = JSON.stringify({
        event_id: 'evt-0',
        event_type: 'report.created',
        entity_id: 'rep-0',
        payload: {},
      });

      const events: RealtimeEvent[] = [];
      service.subscribe((evt) => events.push(evt));

      service.handleIncomingEvent('report.created', replayedOldest);
      expect(events.length).toBe(1);
    });
  });

  describe('4. Centralized Query Invalidation Exactness', () => {
    it('report.created invalidates lists, geo, dashboard, analytics, and queue keys', () => {
      service.initialize(queryClient);

      const rawEvent = JSON.stringify({
        event_id: 'evt-rep-create',
        event_type: 'report.created',
        entity_id: 'rep-101',
        payload: {},
      });

      MockEventSource.instances[0].emitEvent('report.created', rawEvent);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.geoAll() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.verificationQueues() });
    });

    it('report.verification_changed invalidates detail, lists, geo, dashboard, analytics, and queue keys', () => {
      service.initialize(queryClient);

      const rawEvent = JSON.stringify({
        event_id: 'evt-rep-verify',
        event_type: 'report.verification_changed',
        entity_id: 'rep-202',
        payload: { previous_status: 'PENDING', new_status: 'VERIFIED' },
      });

      MockEventSource.instances[0].emitEvent('report.verification_changed', rawEvent);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail('rep-202') });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.geoAll() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.verificationQueues() });
    });

    it('report.intelligence_ready invalidates detail, lists, and analytics keys', () => {
      service.initialize(queryClient);

      const rawEvent = JSON.stringify({
        event_id: 'evt-rep-intel',
        event_type: 'report.intelligence_ready',
        entity_id: 'rep-303',
        payload: { credibility_score: 0.85 },
      });

      MockEventSource.instances[0].emitEvent('report.intelligence_ready', rawEvent);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.detail('rep-303') });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.lists() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
    });

    it('cluster.updated invalidates geoAll, incidents.all, and dashboard.all keys', () => {
      service.initialize(queryClient);

      const rawEvent = JSON.stringify({
        event_id: 'evt-cluster-1',
        event_type: 'cluster.updated',
        entity_id: 'clus-404',
        payload: { member_count: 5 },
      });

      MockEventSource.instances[0].emitEvent('cluster.updated', rawEvent);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.geoAll() });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
    });

    it('system.resync_required triggers broad authoritative cache invalidation', () => {
      service.initialize(queryClient);

      const rawEvent = JSON.stringify({
        event_id: 'evt-resync-1',
        event_type: 'system.resync_required',
        entity_id: 'system',
        payload: { reason: 'RESYNC_REQUIRED' },
      });

      MockEventSource.instances[0].emitEvent('system.resync_required', rawEvent);

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: incidentKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: analyticsKeys.all });
    });
  });

  describe('5. Subscriber Registration & Cleanup', () => {
    it('subscribers receive events and unsubscribe cleanly', () => {
      service.initialize(queryClient);
      const events: RealtimeEvent[] = [];
      const unsubscribe = service.subscribe((evt) => events.push(evt));

      MockEventSource.instances[0].emitEvent(
        'report.created',
        JSON.stringify({ event_id: 'e1', event_type: 'report.created', entity_id: 'r1', payload: {} })
      );
      expect(events.length).toBe(1);

      unsubscribe();

      MockEventSource.instances[0].emitEvent(
        'report.created',
        JSON.stringify({ event_id: 'e2', event_type: 'report.created', entity_id: 'r2', payload: {} })
      );
      // No new events received by unsubscribed listener
      expect(events.length).toBe(1);
    });

    it('destroy cleans up all subscribers and EventSource', () => {
      service.initialize(queryClient);
      const instance = MockEventSource.instances[0];

      service.destroy();
      expect(service.getState()).toBe('closed');
      expect(instance.readyState).toBe(2);
    });
  });
});
