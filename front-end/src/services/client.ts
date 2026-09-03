// Centralized HTTP Client with Error Normalization & Signal Support

import { ApiErrorEnvelope } from "@/types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  public code: string;
  public status: number;
  public details?: unknown[];

  constructor(
    message: string,
    code: string = "HTTP_ERROR",
    status: number = 500,
    details?: unknown[],
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions extends RequestInit {
  signal?: AbortSignal;
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Automatically attach Bearer token if present in sessionStorage
  const token =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem("nwbda_auth_token")
      : null;
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Same-origin session cookies / bearer support
  const finalOptions: RequestInit = {
    ...options,
    headers,
  };

  let res: Response;
  try {
    res = await fetch(url, finalOptions);
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new ApiError(
      err instanceof Error
        ? err.message
        : "Network request failed. Please check your connectivity.",
      "NETWORK_ERROR",
      0,
    );
  }

  let data: Record<string, unknown> | null = null;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = (await res.json()) as Record<string, unknown>;
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    if (res.status === 401 && token && typeof window !== "undefined") {
      window.dispatchEvent(new Event("nwbda:auth-expired"));
    }

    let errorMsg = `HTTP Error ${res.status}`;
    let errorCode: string;
    switch (res.status) {
      case 400:
        errorCode = "BAD_REQUEST";
        break;
      case 404:
        errorCode = "RESOURCE_NOT_FOUND";
        break;
      case 409:
        errorCode = "RESOURCE_CONFLICT";
        break;
      case 422:
        errorCode = "VALIDATION_ERROR";
        break;
      case 429:
        errorCode = "RATE_LIMITED";
        errorMsg = "Request limit exceeded. Please wait before retrying.";
        break;
      case 500:
        errorCode = "INTERNAL_SERVER_ERROR";
        break;
      case 503:
        errorCode = "SERVICE_UNAVAILABLE";
        break;
      default:
        errorCode = "HTTP_ERROR";
    }
    let details: unknown[] | undefined;

    if (data) {
      if (data.error && typeof data.error === "object") {
        const env = data.error as ApiErrorEnvelope;
        errorMsg = env.message || errorMsg;
        errorCode = env.code || errorCode;
        details = env.details as unknown[];
      } else if (data.detail) {
        if (typeof data.detail === "string") {
          errorMsg = data.detail;
        } else if (typeof data.detail === "object") {
          const det = data.detail as {
            message?: string;
            code?: string;
            details?: unknown[];
          };
          errorMsg = det.message || errorMsg;
          errorCode = det.code || errorCode;
          details = det.details;
        }
      } else if (typeof data.message === "string") {
        errorMsg = data.message;
      }
    }

    throw new ApiError(errorMsg, errorCode, res.status, details);
  }

  return data as unknown as T;
}
