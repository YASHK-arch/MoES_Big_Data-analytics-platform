// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ImageForensicsCard } from '@/components/incident/ImageForensicsCard';
import { IncidentImageForensicsDetail } from '@/types/incident';
import '@/i18n';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

describe('ImageForensicsCard Component', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  const mockConsistentForensics: IncidentImageForensicsDetail = {
    overall_verdict: 'SUPPORTS',
    total_credibility_adjustment: 0.05,
    image_count: 1,
    is_simulated: false,
    images: [
      {
        id: 'img-finding-1',
        media_id: 'media-1',
        sha256: 'a1b2c3d4e5f67890abcdef1234567890abcdef12',
        phash: 'c629293939f68629',
        dhash: '0000000000000000',
        has_exif: true,
        exif_timestamp_utc: '2026-08-15T10:00:00Z',
        timezone_assumed_ist: false,
        time_verdict: 'SUPPORTS',
        time_difference: '0.50 hours',
        location_verdict: 'SUPPORTS',
        location_difference: '1.20 km',
        reuse_verdict: 'SUPPORTS',
        matched_incident_ids: [],
        overall_verdict: 'SUPPORTS',
        credibility_adjustment: 0.05,
        checks: [
          {
            check_type: 'EXIF_TIME',
            verdict: 'SUPPORTS',
            difference: '0.50 hours',
            matched_incident_ids: [],
          },
        ],
        is_simulated: false,
      },
    ],
  };

  it('renders CONSISTENT / SUPPORTS verdict with time gap, distance, and positive credibility', () => {
    mockUseAuth.mockReturnValue({ isOperator: false, isAdmin: false });

    render(
      <MemoryRouter>
        <ImageForensicsCard forensics={mockConsistentForensics} />
      </MemoryRouter>
    );

    expect(screen.getByTestId('image-forensics-card')).toBeTruthy();
    expect(screen.getByText('Image Forensics & EXIF Consistency')).toBeTruthy();
    expect(screen.getByText('+0.05 Credibility')).toBeTruthy();
    expect(screen.getByText(/0.50 hours/)).toBeTruthy();
    expect(screen.getByText(/1.20 km/)).toBeTruthy();
    expect(screen.getByText('No cross-incident reuse detected')).toBeTruthy();
  });

  it('renders CONTRADICTS verdict with reuse detected and operator clickable link (P5)', () => {
    mockUseAuth.mockReturnValue({ isOperator: true, isAdmin: false });

    const reusedIncidentId = 'b848c087-c1d0-424b-bb15-05e839e0839e';
    const mockReuseForensics: IncidentImageForensicsDetail = {
      overall_verdict: 'CONTRADICTS',
      total_credibility_adjustment: -0.05,
      image_count: 1,
      is_simulated: false,
      images: [
        {
          id: 'img-finding-2',
          media_id: 'media-2',
          sha256: '1234567890abcdef1234567890abcdef12345678',
          phash: 'ffff0000ffff0000',
          has_exif: false,
          timezone_assumed_ist: false,
          time_verdict: 'NEUTRAL',
          location_verdict: 'NEUTRAL',
          reuse_verdict: 'CONTRADICTS',
          matched_incident_ids: [reusedIncidentId],
          overall_verdict: 'CONTRADICTS',
          credibility_adjustment: -0.05,
          checks: [],
          is_simulated: false,
        },
      ],
    };

    render(
      <MemoryRouter>
        <ImageForensicsCard forensics={mockReuseForensics} />
      </MemoryRouter>
    );

    expect(screen.getByText('-0.05 Credibility')).toBeTruthy();
    expect(screen.getByText('Reused in Incident:')).toBeTruthy();

    // Verify clickable link for operator
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe(`/incidents/${reusedIncidentId}`);
  });

  it('renders NEUTRAL verdict with missing EXIF explanation without penalty (P1)', () => {
    mockUseAuth.mockReturnValue({ isOperator: false, isAdmin: false });

    const mockNeutralForensics: IncidentImageForensicsDetail = {
      overall_verdict: 'NEUTRAL',
      total_credibility_adjustment: 0.0,
      image_count: 1,
      is_simulated: false,
      images: [
        {
          id: 'img-finding-3',
          media_id: 'media-3',
          sha256: '9999999999999999999999999999999999999999',
          phash: '1111111111111111',
          has_exif: false,
          timezone_assumed_ist: false,
          time_verdict: 'NEUTRAL',
          location_verdict: 'NEUTRAL',
          reuse_verdict: 'SUPPORTS',
          matched_incident_ids: [],
          overall_verdict: 'NEUTRAL',
          credibility_adjustment: 0.0,
          checks: [],
          is_simulated: false,
        },
      ],
    };

    render(
      <MemoryRouter>
        <ImageForensicsCard forensics={mockNeutralForensics} />
      </MemoryRouter>
    );

    // Missing EXIF reason should be displayed
    expect(
      screen.getAllByText('No camera metadata found (treated as neutral)').length
    ).toBeGreaterThan(0);
    // No credibility adjustment badge rendered when adjustment is 0
    expect(screen.queryByText(/Credibility$/)).toBeNull();
  });

  it('renders SIMULATED badge when is_simulated is true', () => {
    mockUseAuth.mockReturnValue({ isOperator: false, isAdmin: false });

    const mockSimForensics: IncidentImageForensicsDetail = {
      ...mockConsistentForensics,
      is_simulated: true,
    };

    render(
      <MemoryRouter>
        <ImageForensicsCard forensics={mockSimForensics} />
      </MemoryRouter>
    );

    expect(screen.getByText('SIMULATED')).toBeTruthy();
  });

  it('returns null when forensics data is empty or missing', () => {
    const { container } = render(
      <MemoryRouter>
        <ImageForensicsCard forensics={null} />
      </MemoryRouter>
    );
    expect(container.firstChild).toBeNull();
  });
});
