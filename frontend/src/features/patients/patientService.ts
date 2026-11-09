/**
 * Patient API service for LabFlow per Doc 03 §5.1, §6.2 and Doc 04 §8.5.
 */

import { apiRequest, ApiError } from "../../lib/apiClient";
import type {
  DuplicateWarningError,
  PatientCreateInput,
  PatientDetail,
  PatientSummary,
  PatientUpdateInput,
} from "./types";

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
    const data = await apiRequest<
      PatientSummary[] | { results: PatientSummary[] }
    >("/patients", {
      query: {
        q: params.q,
        branch_id: params.branchId,
      },
    });

    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.results)) return data.results;
    return [];
  },

  async getPatient(id: string): Promise<PatientDetail> {
    try {
      return await apiRequest<PatientDetail>(`/patients/${id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(`Patient not found or inaccessible (${err.status})`);
      }
      throw err;
    }
  },

  async createPatient(input: PatientCreateInput): Promise<PatientSummary> {
    try {
      return await apiRequest<PatientSummary>("/patients", {
        method: "POST",
        body: {
          name: input.name,
          phone: input.phone,
          sex: input.sex,
          date_of_birth: input.date_of_birth || null,
          branch_id: input.branch_id,
          confirm_duplicate: input.confirm_duplicate ?? false,
        },
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const errorData = (err.problem?.error || err.problem) as unknown as
          DuplicateWarningError | undefined;
        if (errorData?.code === "possible_duplicate") {
          throw new DuplicatePatientError(errorData);
        }
      }
      throw err;
    }
  },

  async updatePatient(
    id: string,
    input: PatientUpdateInput,
    version?: number,
  ): Promise<PatientDetail> {
    const headers: Record<string, string> = {};
    if (version !== undefined) {
      headers["If-Match"] = `"${version}"`;
    }

    try {
      return await apiRequest<PatientDetail>(`/patients/${id}`, {
        method: "PATCH",
        headers,
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Update failed (${err.status})`);
      }
      throw err;
    }
  },

  async deletePatient(id: string): Promise<void> {
    try {
      await apiRequest<void>(`/patients/${id}`, {
        method: "DELETE",
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(`Delete failed (${err.status})`);
      }
      throw err;
    }
  },
};
