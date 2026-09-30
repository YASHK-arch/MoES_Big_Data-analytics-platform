// Typed adapter converting GeoJSON FeatureCollection into map-consumable incident points

import { GeoJSONFeatureCollection } from '@/types';

export interface MapIncidentPoint {
  id: string;
  tracking_id: string;
  title: string;
  severity: string;
  verification_status: string;
  occurred_at: string | null;
  location: {
    latitude: number;
    longitude: number;
    name?: string | null;
  };
  category?: {
    code: string;
    title: string;
  };
  credibility_score?: number | null;
  readiness?: string | null;
  is_demo?: boolean;
}

/**
 * Transforms PostGIS GeoJSON FeatureCollection to clean MapIncidentPoint models.
 * GeoJSON geometry standard: coordinates[0] = longitude, coordinates[1] = latitude.
 */
export function geoJSONToMapPoints(
  featureCollection?: GeoJSONFeatureCollection | null
): MapIncidentPoint[] {
  if (!featureCollection || !featureCollection.features) return [];

  return featureCollection.features
    .filter(
      (f) =>
        f.geometry?.coordinates &&
        f.geometry.coordinates.length >= 2 &&
        f.geometry.coordinates[1] != null &&
        f.geometry.coordinates[0] != null
    )
    .map((f) => ({
      id: f.properties.id,
      tracking_id: f.properties.tracking_id,
      title: f.properties.title,
      severity: f.properties.severity,
      verification_status: f.properties.verification_status,
      occurred_at: f.properties.occurred_at,
      location: {
        latitude: f.geometry.coordinates[1],
        longitude: f.geometry.coordinates[0],
        name: f.properties.location_name,
      },
      category: {
        code: f.properties.category_code,
        title: f.properties.category_code.replace(/_/g, ' '),
      },
      credibility_score: f.properties.credibility_score,
      readiness: f.properties.readiness,
      is_demo: f.properties.is_demo,
    }));
}
