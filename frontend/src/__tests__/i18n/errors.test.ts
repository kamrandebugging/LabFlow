import { describe, expect, it } from "vitest";
import { messageForError } from "../../lib/errors";
import { ApiError } from "../../lib/apiClient";

describe("messageForError", () => {
  it("translates known error codes when available in local namespace", () => {
    const mockT = (key: string) => {
      if (key === "errors.conflict") {
        return "Record changed. Please reload.";
      }
      return key;
    };
    const err = new ApiError(
      409,
      { code: "invalid_state_transition" },
      "Failed",
    );
    expect(messageForError(err, mockT)).toBe("Record changed. Please reload.");
  });

  it("falls back to common: namespace when local namespace returns raw key", () => {
    const mockT = (key: string) => {
      if (key === "common:errors.generic") {
        return "Something went wrong. Please try again.";
      }
      return key; // simulates untranslated key returning itself
    };
    const err = new Error("unknown error");
    expect(messageForError(err, mockT)).toBe(
      "Something went wrong. Please try again.",
    );
  });

  it("maps HTTP status 404 to common:errors.not_found", () => {
    const mockT = (key: string) => {
      if (key === "common:errors.not_found") {
        return "The requested record was not found.";
      }
      return key;
    };
    const err = new ApiError(404, null, "Not found");
    expect(messageForError(err, mockT)).toBe(
      "The requested record was not found.",
    );
  });

  it("never returns raw 'errors.generic' string even if t returns key", () => {
    const mockT = (key: string) => key; // completely unmapped t
    const err = new Error("raw error");
    const result = messageForError(err, mockT);
    expect(result).not.toBe("errors.generic");
    expect(result).toBe("Something went wrong. Please try again.");
  });
});
