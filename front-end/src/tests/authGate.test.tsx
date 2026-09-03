// @vitest-environment jsdom

import React from "react";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { UserProfile } from "@/services/authApi";
import { AuthGate } from "@/App";
import { useAuth } from "@/context/AuthContext";

vi.mock("@/context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/pages/LoginPage", () => ({
  LoginPage: () => <div data-testid="login-page">Login page</div>,
}));

const mockedUseAuth = vi.mocked(useAuth);

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderAuthGate(isAuthenticated: boolean, role?: UserProfile["role"]) {
  mockedUseAuth.mockReturnValue({
    token: isAuthenticated ? "token" : null,
    user: role ? ({ role } as UserProfile) : null,
    operator: null,
    isAuthenticated,
    isOperator: role === "OPERATOR" || role === "ADMIN",
    isCitizen: role === "CITIZEN",
    isAdmin: role === "ADMIN",
    isLoading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    updateSavedLocation: vi.fn(),
  });

  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthGate />
      <LocationProbe />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthGate root route", () => {
  it("renders the login page when unauthenticated", () => {
    const view = renderAuthGate(false);

    expect(view.getByTestId("login-page")).toBeTruthy();
    expect(view.getByTestId("location").textContent).toBe("/");
  });

  it.each([
    ["ADMIN", "/dashboard"],
    ["OPERATOR", "/admin/queue"],
    ["CITIZEN", "/citizen-dashboard"],
  ] as const)("redirects %s users to %s", async (role, destination) => {
    const view = renderAuthGate(true, role);

    await waitFor(() => {
      expect(view.getByTestId("location").textContent).toBe(destination);
    });
  });
});
