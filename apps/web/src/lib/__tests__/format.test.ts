import { describe, expect, it } from "vitest";

import { cce10, clampWeights, formatDate, formatPct, formatTL, lotQuantity, rankDeltaLabel, signClass, weightsEqual } from "../format";

describe("formatTL", () => {
  it("formats Turkish lira and handles missing values", () => {
    expect(formatTL(1234567)).toContain("1.234.567");
    expect(formatTL(null)).toBe("—");
    expect(formatTL(Number.NaN)).toBe("—");
  });
});

describe("formatPct", () => {
  it("uses comma decimal separator and optional sign", () => {
    expect(formatPct(0.1234)).toBe("12,34 %");
    expect(formatPct(0.05, 1, true)).toBe("+5,0 %");
    expect(formatPct(-0.05, 1, true)).toBe("-5,0 %");
    expect(formatPct(undefined)).toBe("—");
  });
});

describe("formatDate", () => {
  it("converts ISO to dd.mm.yyyy", () => {
    expect(formatDate("2026-09-19")).toBe("19.09.2026");
    expect(formatDate(null)).toBe("—");
  });
});

describe("signClass", () => {
  it("maps sign to css class", () => {
    expect(signClass(1)).toBe("pos");
    expect(signClass(-1)).toBe("neg");
    expect(signClass(0)).toBe("");
    expect(signClass(null)).toBe("");
  });
});

describe("clampWeights", () => {
  it("clamps to [0,1], fills missing keys and rounds to 2 decimals", () => {
    const w = clampWeights({ return: 1.4, dividend: -0.2, liquidity: 0.555 });
    expect(w).toEqual({ return: 1, dividend: 0, liquidity: 0.56, risk: 0 });
  });
  it("compares weights with tolerance", () => {
    expect(weightsEqual({ return: 0.8, dividend: 0.6, liquidity: 0.6, risk: 0.8 }, { return: 0.8, dividend: 0.6, liquidity: 0.6, risk: 0.8 })).toBe(true);
    expect(weightsEqual({ return: 0.8, dividend: 0.6, liquidity: 0.6, risk: 0.8 }, { return: 0.7, dividend: 0.6, liquidity: 0.6, risk: 0.8 })).toBe(false);
  });
});

describe("cce10", () => {
  it("reproduces the seminar C29 score with balanced weights", () => {
    const weights = { return: 0.8, dividend: 0.6, liquidity: 0.6, risk: 0.8 };
    const c29 = { return: 0.84, dividend: 0.33, liquidity: 0.84, risk: 0.55 };
    expect(cce10(c29, weights)).toBeCloseTo(0.4535, 4); // seminerde ≈0.454
  });
});

describe("lotQuantity", () => {
  it("floors to whole lots and guards invalid inputs", () => {
    expect(lotQuantity(10000, 0.6, 101)).toBe(59);
    expect(lotQuantity(10000, 0.6, 0)).toBe(0);
    expect(lotQuantity(0, 0.6, 10)).toBe(0);
  });
});

describe("rankDeltaLabel", () => {
  it("renders arrows", () => {
    expect(rankDeltaLabel(0)).toBe("=");
    expect(rankDeltaLabel(2)).toBe("▲2");
    expect(rankDeltaLabel(-3)).toBe("▼3");
  });
});
