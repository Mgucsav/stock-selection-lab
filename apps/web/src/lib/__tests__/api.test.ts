import { describe, expect, it } from "vitest";

import { ApiError, describeError } from "../api";

describe("describeError", () => {
  it("explains network failures with the backend address", () => {
    expect(describeError(new ApiError("Ağ hatası", 0))).toContain("Backend'e ulaşılamadı");
  });
  it("passes through server detail messages", () => {
    expect(describeError(new ApiError("Karar tarihi veri tarihinden sonra olamaz.", 400))).toBe("Karar tarihi veri tarihinden sonra olamaz.");
  });
  it("handles unknown values", () => {
    expect(describeError("x")).toBe("Bilinmeyen hata.");
  });
});
