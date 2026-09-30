// Canonical Domain & Operational Exports

export * from './enums';
export * from './api';
export * from './incident';
export * from './credibility';
export * from './intelligence';
export * from './evidence';
export * from './observation';
export * from './duplicate';
export * from './geo';
export * from './verification';
export * from './report';
export * from './admin';
export * from './analytics';
export * from './realtime';

export interface HealthStatus {
  status: string;
  service: string;
  environment: string;
  version: string;
}
