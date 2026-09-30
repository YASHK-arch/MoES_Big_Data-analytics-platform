import { describe, it, expect, vi, beforeEach } from 'vitest';
import { incidentApi } from '@/services/incidentApi';
import { dashboardApi } from '@/services/dashboardApi';

// Mock global fetch
const fetchMock = vi.fn();
global.fetch = fetchMock;

describe('Demo Data Filter & Badging Contract', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, data: [] }),
    });
  });

  it('serializes hide_demo=true in incidentApi.listIncidents', async () => {
    await incidentApi.listIncidents({ hide_demo: true, category: 'FOG' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('hide_demo=true');
    expect(calledUrl).toContain('category=FOG');
  });

  it('serializes hide_demo=true in incidentApi.getGeoIncidents', async () => {
    await incidentApi.getGeoIncidents(undefined, { status: 'VERIFIED', hide_demo: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('hide_demo=true');
    expect(calledUrl).toContain('status=VERIFIED');
  });

  it('serializes hide_demo=true in dashboardApi.getSummary', async () => {
    await dashboardApi.getSummary({ time_range: '24h', hide_demo: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('hide_demo=true');
    expect(calledUrl).toContain('time_range=24h');
  });
});
