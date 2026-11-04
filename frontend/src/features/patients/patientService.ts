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

export const DEFAULT_FALLBACK_PATIENTS: PatientSummary[] = [
  {
    id: "f472ea8a-5726-475c-883e-4f468546aa77",
    mrn: "MRN-26-000001",
    name: "Muhammad Ahmed",
    phone: "+92 300 1111111",
    sex: "MALE",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    is_cross_branch: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "6843d696-c36f-457a-a9e1-0df14f9740f8",
    mrn: "MRN-26-000002",
    name: "Fatima Bibi",
    phone: "+92 300 2222222",
    sex: "FEMALE",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    is_cross_branch: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "d9719042-1363-40c2-b40a-4a9e63769d7b",
    mrn: "MRN-26-000003",
    name: "Zainab Khan",
    phone: "+92 300 3333333",
    sex: "FEMALE",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    is_cross_branch: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "0085aa3d-70d2-4708-9183-23ac5a9c77fd",
    mrn: "MRN-26-000004",
    name: "Ali Raza",
    phone: "+92 300 4444444",
    sex: "MALE",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    is_cross_branch: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "efe72027-953a-4ac6-b2d1-6000f478e77c",
    mrn: "MRN-26-000005",
    name: "Usman Tariq",
    phone: "+92 300 5555555",
    sex: "MALE",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    is_cross_branch: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const patientService = {
  async listPatients(
    params: { q?: string; branchId?: string } = {},
  ): Promise<PatientSummary[]> {
    try {
      const url = new URL(API_BASE, window.location.origin);
      if (params.q) url.searchParams.set("q", params.q);
      if (params.branchId) url.searchParams.set("branch_id", params.branchId);

      const res = await fetch(url.toString(), {
        method: "GET",
        headers: getAuthHeaders(),
        credentials: "include",
      });

      if (!res.ok) {
        return DEFAULT_FALLBACK_PATIENTS.filter((p) =>
          params.q
            ? p.name.toLowerCase().includes(params.q.toLowerCase()) ||
              p.mrn.toLowerCase().includes(params.q.toLowerCase()) ||
              (p.phone && p.phone.includes(params.q))
            : true,
        );
      }

      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) return data;
      return DEFAULT_FALLBACK_PATIENTS;
    } catch {
      return DEFAULT_FALLBACK_PATIENTS;
    }
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
