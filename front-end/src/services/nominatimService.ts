/**
 * OpenStreetMap Nominatim Geocoding and Reverse-Geocoding Service.
 *
 * Adheres strictly to Nominatim Usage Policy:
 * - Includes a custom User-Agent identifying the application
 * - In-memory client-side cache for repeated queries
 * - City-sized bounding box computation with named constant CITY_BBOX_DELTA = 0.5
 */

export const CITY_BBOX_DELTA = 0.5; // ±0.5° (~55km) city-sized bounding box

export interface GeocodedLocation {
  name: string;
  displayName: string;
  lat: number;
  lon: number;
  bbox: string; // "min_lon,min_lat,max_lon,max_lat"
  type?: string;
}

export const DEFAULT_NATIONAL_LOCATION: GeocodedLocation = {
  name: 'All India',
  displayName: 'National Overview (All India)',
  lat: 20.5937,
  lon: 78.9629,
  bbox: '', // empty means national/unconstrained
};

const NOMINATIM_BASE_URL = 'https://nominatim.openstreetmap.org';
const NOMINATIM_HEADERS: HeadersInit = {
  'User-Agent': 'NWBDA-Platform/1.0 (sih26069@weather-platform.gov.in)',
  Accept: 'application/json',
};

// In-memory cache for reverse and search results
const reverseCache = new Map<string, GeocodedLocation>();
const searchCache = new Map<string, GeocodedLocation[]>();

/**
 * Calculates a valid min_lon,min_lat,max_lon,max_lat bounding box around coordinates.
 */
export function calculateBbox(lat: number, lon: number, delta: number = CITY_BBOX_DELTA): string {
  const minLon = Math.max(-180, lon - delta);
  const minLat = Math.max(-90, lat - delta);
  const maxLon = Math.min(180, lon + delta);
  const maxLat = Math.min(90, lat + delta);
  return `${minLon.toFixed(4)},${minLat.toFixed(4)},${maxLon.toFixed(4)},${maxLat.toFixed(4)}`;
}

/**
 * Reverse-geocodes latitude & longitude to an Indian city/locality name via Nominatim.
 */
export async function reverseGeocode(lat: number, lon: number): Promise<GeocodedLocation> {
  const cacheKey = `${lat.toFixed(3)}_${lon.toFixed(3)}`;
  if (reverseCache.has(cacheKey)) {
    return reverseCache.get(cacheKey)!;
  }

  const bbox = calculateBbox(lat, lon);

  try {
    const url = `${NOMINATIM_BASE_URL}/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1`;
    const res = await fetch(url, { headers: NOMINATIM_HEADERS });

    if (!res.ok) {
      throw new Error(`Nominatim reverse HTTP ${res.status}`);
    }

    const data = await res.json();
    const address = data.address || {};
    const cityName =
      address.city ||
      address.town ||
      address.municipality ||
      address.county ||
      address.state_district ||
      address.state ||
      data.name ||
      'Detected Location';

    const result: GeocodedLocation = {
      name: cityName,
      displayName: data.display_name || cityName,
      lat,
      lon,
      bbox,
      type: data.type,
    };

    reverseCache.set(cacheKey, result);
    return result;
  } catch (err) {
    console.warn('Reverse geocoding failed; using coordinate fallback:', err);
    const fallback: GeocodedLocation = {
      name: `${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`,
      displayName: `Area around ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`,
      lat,
      lon,
      bbox,
    };
    return fallback;
  }
}

/**
 * Searches for Indian cities or districts by name via Nominatim search.
 */
export async function searchCity(query: string): Promise<GeocodedLocation[]> {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed || trimmed.length < 2) {
    return [];
  }

  if (searchCache.has(trimmed)) {
    return searchCache.get(trimmed)!;
  }

  try {
    const url = `${NOMINATIM_BASE_URL}/search?format=jsonv2&q=${encodeURIComponent(
      query
    )}&countrycodes=in&limit=6&addressdetails=1`;
    const res = await fetch(url, { headers: NOMINATIM_HEADERS });

    if (!res.ok) {
      throw new Error(`Nominatim search HTTP ${res.status}`);
    }

    const data: Array<{
      display_name: string;
      lat: string;
      lon: string;
      name?: string;
      type?: string;
      address?: Record<string, string>;
    }> = await res.json();

    const results: GeocodedLocation[] = data.map((item) => {
      const lat = parseFloat(item.lat);
      const lon = parseFloat(item.lon);
      const address = item.address || {};
      const cityName =
        address.city ||
        address.town ||
        address.municipality ||
        address.county ||
        address.state_district ||
        item.name ||
        item.display_name.split(',')[0];

      return {
        name: cityName,
        displayName: item.display_name,
        lat,
        lon,
        bbox: calculateBbox(lat, lon),
        type: item.type,
      };
    });

    searchCache.set(trimmed, results);
    return results;
  } catch (err) {
    console.warn('Nominatim city search failed:', err);
    return [];
  }
}

export { searchCity as searchLocations };
