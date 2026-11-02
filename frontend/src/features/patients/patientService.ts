/**
 * Patient API service for LabFlow per Doc 03 §5.1, §6.2 and Doc 04 §8.5.
 */

import { useAuthStore } from "../auth/authStore";
import type {
  DuplicateWarningError,
  PatientCreateInput,
  PatientDetail,
  PatientSummary,
  PatientUpdateInput,
} from "./types";

const API_BASE = "/api/v1/patients";

function getAuthHeaders(
  extraHeaders: Record<string, string> = {},
): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export class DuplicatePatientError extends Error {
  candidates: DuplicateWarningError["candidates"];

  constructor(data: DuplicateWarningError) {
    super(data.message || "Possible duplicate patient detected.");
    this.name = "DuplicatePatientError";
    this.candidates = data.candidates || [];
  }
}

export const patientService = {
  async listPatients(
    params: { q?: string; branchId?: string } = {},
  ): Promise<PatientSummary[]> {
    const url = new URL(API_BASE, window.location.origin);
    if (params.q) url.searchParams.set("q", params.q);
    if (params.branchId) url.searchParams.set("branch_id", params.branchId);

    const res = await fetch(url.toString(), {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Failed to fetch patients (${res.status})`);
    }

    return res.json();
  },

  async getPatient(id: string): Promise<PatientDetail> {
    const res = await fetch(`${API_BASE}/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Patient not found or inaccessible (${res.status})`);
    }

    return res.json();
  },

  async createPatient(input: PatientCreateInput): Promise<PatientSummary> {
    const res = await fetch(API_BASE, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify({
        name: input.name,
        phone: input.phone,
        sex: input.sex,
        date_of_birth: input.date_of_birth || null,
        branch_id: input.branch_id,
        confirm_duplicate: input.confirm_duplicate ?? false,
      }),
    });

    if (res.status === 409) {
      const errData = await res.json();
      if (errData?.error?.code === "possible_duplicate") {
        throw new DuplicatePatientError(errData.error);
      }
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const message =
        err?.error?.message ||
        Object.values(err)[0] ||
        `Registration failed (${res.status})`;
      throw new Error(String(message));
    }

    return res.json();
  },

  async updatePatient(
    id: string,
    input: PatientUpdateInput,
    version?: number,
  ): Promise<PatientDetail> {
    const extraHeaders: Record<string, string> = {};
    if (version !== undefined) {
      extraHeaders["If-Match"] = `"${version}"`;
    }

    const res = await fetch(`${API_BASE}/${id}`, {
      method: "PATCH",
      headers: getAuthHeaders(extraHeaders),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err?.error?.message || `Update failed (${res.status})`);
    }

    return res.json();
  },

  async deletePatient(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Delete failed (${res.status})`);
    }
  },
};
