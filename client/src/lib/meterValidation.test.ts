import { describe, expect, it } from "vitest";
import { isValidMeterCode, normalizeMeterCode } from "./meterValidation";

describe("meter code validation", () => {
  it("keeps only digits and limits the code to 20 characters", () => {
    expect(normalizeMeterCode("12ab34-5678901234567890")).toBe("12345678901234567890");
  });

  it("accepts exactly 20 digits and rejects every other length", () => {
    expect(isValidMeterCode("12345678901234567890")).toBe(true);
    expect(isValidMeterCode("1234567890123456789")).toBe(false);
    expect(isValidMeterCode("123456789012345678901")).toBe(false);
  });
});
