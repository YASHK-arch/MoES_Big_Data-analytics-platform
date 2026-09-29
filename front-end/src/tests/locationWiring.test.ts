// Tests for Phase 2: Location-Based Frontend Wiring (C3)

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  calculateBbox,
  CITY_BBOX_DELTA,
  DEFAULT_NATIONAL_LOCATION,
  reverseGeocode,
  searchCity,
} from '@/services/nominatimService';

describe('Phase 2 Location Wiring Tests (C3)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('1. Calculates valid ±0.5° bounding box correctly around coordinates', () => {
    const lat = 12.9716;
    const lon = 77.5946;
    const bbox = calculateBbox(lat, lon, CITY_BBOX_DELTA);

    const [minLon, minLat, maxLon, maxLat] = bbox.split(',').map(Number);

    expect(CITY_BBOX_DELTA).toBe(0.5);
    expect(minLon).toBeCloseTo(lon - 0.5, 4);
    expect(minLat).toBeCloseTo(lat - 0.5, 4);
    expect(maxLon).toBeCloseTo(lon + 0.5, 4);
    expect(maxLat).toBeCloseTo(lat + 0.5, 4);
    expect(maxLon - minLon).toBeCloseTo(1.0, 4);
    expect(maxLat - minLat).toBeCloseTo(1.0, 4);
  });

  it('2. Clamps bounding box within valid geographic boundaries [-180, 180] and [-90, 90]', () => {
    // Near north pole
    const northBbox = calculateBbox(89.8, 179.8, 0.5);
    const [nMinLon, nMinLat, nMaxLon, nMaxLat] = northBbox.split(',').map(Number);
    expect(nMaxLat).toBe(90.0);
    expect(nMaxLon).toBe(180.0);
    expect(nMinLat).toBe(89.3);
    expect(nMinLon).toBe(179.3);
  });

  it('3. Reverse-geocodes coordinates with Nominatim User-Agent header and extracts city name', async () => {
    const mockResponse = {
      name: 'Bengaluru',
      display_name: 'Bengaluru, Bangalore Urban, Karnataka, India',
      address: {
        city: 'Bengaluru',
        state_district: 'Bangalore Urban',
        state: 'Karnataka',
        country: 'India',
      },
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockResponse,
    });
    global.fetch = fetchMock;

    const loc = await reverseGeocode(12.9716, 77.5946);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const callUrl = fetchMock.mock.calls[0][0] as string;
    const callOpts = fetchMock.mock.calls[0][1] as RequestInit;

    expect(callUrl).toContain('lat=12.9716');
    expect(callUrl).toContain('lon=77.5946');
    expect((callOpts.headers as Record<string, string>)['User-Agent']).toContain('NWBDA-Platform');

    expect(loc.name).toBe('Bengaluru');
    expect(loc.lat).toBe(12.9716);
    expect(loc.lon).toBe(77.5946);
    expect(loc.bbox).toBe('77.0946,12.4716,78.0946,13.4716');
  });

  it('4. Searches cities by query string filtered to country code in', async () => {
    const mockSearchResults = [
      {
        name: 'Mumbai',
        display_name: 'Mumbai, Mumbai Suburban, Maharashtra, India',
        lat: '19.0760',
        lon: '72.8777',
        address: {
          city: 'Mumbai',
          state: 'Maharashtra',
        },
      },
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockSearchResults,
    });
    global.fetch = fetchMock;

    const results = await searchCity('Mumbai');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const callUrl = fetchMock.mock.calls[0][0] as string;
    expect(callUrl).toContain('q=Mumbai');
    expect(callUrl).toContain('countrycodes=in');

    expect(results).toHaveLength(1);
    expect(results[0].name).toBe('Mumbai');
    expect(results[0].lat).toBe(19.076);
    expect(results[0].lon).toBe(72.8777);
    expect(results[0].bbox).toBe('72.3777,18.5760,73.3777,19.5760');
  });

  it('5. In-memory cache prevents duplicate Nominatim requests for identical queries', async () => {
    const mockSearchResults = [
      {
        name: 'Chennai',
        display_name: 'Chennai, Tamil Nadu, India',
        lat: '13.0827',
        lon: '80.2707',
      },
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockSearchResults,
    });
    global.fetch = fetchMock;

    const res1 = await searchCity('Chennai');
    const res2 = await searchCity('Chennai');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(res1).toEqual(res2);
  });

  it('6. Default national location provides unconstrained empty bbox fallback', () => {
    expect(DEFAULT_NATIONAL_LOCATION.name).toBe('All India');
    expect(DEFAULT_NATIONAL_LOCATION.bbox).toBe('');
    expect(DEFAULT_NATIONAL_LOCATION.lat).toBe(20.5937);
    expect(DEFAULT_NATIONAL_LOCATION.lon).toBe(78.9629);
  });
});
