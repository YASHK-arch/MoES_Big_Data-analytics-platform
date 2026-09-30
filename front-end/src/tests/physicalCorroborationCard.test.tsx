// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { PhysicalCorroborationCard } from '@/features/reports/components/PhysicalCorroborationCard';
import { PhysicalCorroborationBlock } from '@/types';
import '@/i18n';

describe('PhysicalCorroborationCard Component', () => {
  afterEach(() => {
    cleanup();
  });

  const mockSupportsBlock: PhysicalCorroborationBlock = {
    overall_verdict: 'SUPPORTS',
    overall_provider_status: 'OK',
    total_contribution: 0.0825,
    is_simulated: false,
    items: [
      {
        id: 'item-1',
        variable: 'rainfall_1h',
        observed_value: 72.4,
        unit: 'mm/1h',
        source: 'OPEN_METEO',
        source_type: 'MODEL',
        station_or_grid_id: 'grid_28.63_77.22',
        distance_km: 1.25,
        time_gap_hours: 0.5,
        verdict: 'SUPPORTS',
        weight: 0.6,
        contribution: 0.0825,
        provider_status: 'OK',
        observation_time: '2026-09-30T10:00:00Z',
        explanation: 'Rainfall 72.4 mm/1h exceeds heavy rainfall threshold (64.5 mm)',
        is_simulated: false,
      },
    ],
  };

  it('renders SUPPORTS verdict, observed value, unit, source badge, distance, and explanation', () => {
    render(<PhysicalCorroborationCard corroboration={mockSupportsBlock} enabled={true} />);

    expect(screen.getByTestId('physical-corroboration-card')).toBeTruthy();
    expect(screen.getAllByTestId('verdict-supports').length).toBeGreaterThan(0);
    expect(screen.getByText('72.4 mm/1h')).toBeTruthy();
    expect(screen.getByText('1.3 km')).toBeTruthy();
    expect(screen.getByText('0.5 h')).toBeTruthy();
    expect(screen.getByTestId('source-badge-model')).toBeTruthy();
    expect(screen.getByText('+0.0825')).toBeTruthy();
    expect(
      screen.getByText(/Rainfall 72.4 mm\/1h exceeds heavy rainfall threshold/)
    ).toBeTruthy();
  });

  it('renders CONTRADICTS verdict and negative score impact', () => {
    const mockContradictsBlock: PhysicalCorroborationBlock = {
      overall_verdict: 'CONTRADICTS',
      overall_provider_status: 'OK',
      total_contribution: -0.15,
      is_simulated: false,
      items: [
        {
          id: 'item-2',
          variable: 'rainfall_1h',
          observed_value: 0.0,
          unit: 'mm/1h',
          source: 'IMD_AWS_PUN',
          source_type: 'STATION',
          distance_km: 3.1,
          time_gap_hours: 0.2,
          verdict: 'CONTRADICTS',
          weight: 1.0,
          contribution: -0.15,
          provider_status: 'OK',
          explanation: 'Station measured 0.0 mm/1h during reported cloudburst',
          is_simulated: false,
        },
      ],
    };

    render(<PhysicalCorroborationCard corroboration={mockContradictsBlock} enabled={true} />);

    expect(screen.getAllByTestId('verdict-contradicts').length).toBeGreaterThan(0);
    expect(screen.getByTestId('source-badge-station')).toBeTruthy();
    expect(screen.getByText('-0.1500')).toBeTruthy();
    expect(screen.getByText(/Station measured 0.0 mm\/1h/)).toBeTruthy();
  });

  it('renders NEUTRAL verdict and provider timeout status badge', () => {
    const mockNeutralBlock: PhysicalCorroborationBlock = {
      overall_verdict: 'NEUTRAL',
      overall_provider_status: 'TIMEOUT',
      total_contribution: 0.0,
      is_simulated: false,
      items: [
        {
          id: 'item-3',
          variable: 'wind_speed',
          observed_value: null,
          unit: 'km/h',
          source: 'OPEN_METEO',
          source_type: 'MODEL',
          distance_km: null,
          time_gap_hours: null,
          verdict: 'NEUTRAL',
          weight: 0.6,
          contribution: 0.0,
          provider_status: 'TIMEOUT',
          explanation: 'Provider timeout after 5.0s; fell back to NEUTRAL',
          is_simulated: false,
        },
      ],
    };

    render(<PhysicalCorroborationCard corroboration={mockNeutralBlock} enabled={true} />);

    expect(screen.getAllByTestId('verdict-neutral').length).toBeGreaterThan(0);
    expect(screen.getByText('TIMEOUT')).toBeTruthy();
    expect(screen.getByText(/Provider timeout after 5.0s/)).toBeTruthy();
  });

  it('renders SIMULATED badges when block or item is simulated', () => {
    const mockSimulatedBlock: PhysicalCorroborationBlock = {
      overall_verdict: 'SUPPORTS',
      overall_provider_status: 'OK',
      total_contribution: 0.05,
      is_simulated: true,
      items: [
        {
          id: 'item-sim',
          variable: 'rainfall_1h',
          observed_value: 80.0,
          unit: 'mm/1h',
          source: 'DEMO_FIXTURE_STATION',
          source_type: 'STATION',
          distance_km: 0.8,
          time_gap_hours: 0.1,
          verdict: 'SUPPORTS',
          weight: 1.0,
          contribution: 0.05,
          provider_status: 'OK',
          explanation: 'Deterministic demo scenario fixture observation',
          is_simulated: true,
        },
      ],
    };

    render(<PhysicalCorroborationCard corroboration={mockSimulatedBlock} enabled={true} />);

    expect(screen.getByTestId('overall-simulated-badge')).toBeTruthy();
    expect(screen.getByTestId('source-badge-simulated')).toBeTruthy();
  });

  it('returns null when enabled is false or corroboration is null', () => {
    const { container: containerDisabled } = render(
      <PhysicalCorroborationCard corroboration={mockSupportsBlock} enabled={false} />
    );
    expect(containerDisabled.firstChild).toBeNull();

    const { container: containerNull } = render(
      <PhysicalCorroborationCard corroboration={null} enabled={true} />
    );
    expect(containerNull.firstChild).toBeNull();
  });
});
