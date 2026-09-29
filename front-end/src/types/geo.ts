// PostGIS GeoJSON Types

export interface GeoJSONGeometryPoint {
  type: 'Point';
  coordinates: [number, number]; // [lon, lat]
}

export interface GeoJSONIncidentProperties {
  id: string;
  tracking_id: string;
  title: string;
  category_code: string;
  severity: string;
  verification_status: string;
  credibility_score: number | null;
  credibility_reason?: string | null;
  readiness?: string | null;
  occurred_at: string | null;
  location_name?: string | null;
}

export interface GeoJSONIncidentFeature {
  type: 'Feature';
  geometry: GeoJSONGeometryPoint;
  properties: GeoJSONIncidentProperties;
}

export interface GeoJSONFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJSONIncidentFeature[];
}
