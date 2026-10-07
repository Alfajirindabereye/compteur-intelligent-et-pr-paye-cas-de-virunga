import { describe, expect, it } from "vitest";
import {
  detectAnomalies,
  ingestTelemetry,
  signTelemetryPayload,
  signToken,
  telemetrySchema,
  verifyTelemetrySignature,
  verifyToken,
} from "./energy";

const payload = {
  message_id: "a7d2dba7-6c17-4d6a-8ea9-9c3b45d6d4a1",
  meter_id: "VSE-000001",
  device_timestamp: "2026-08-15T09:00:00.000Z",
  voltage: 220,
  current: 2,
  power: 440,
  energy_consumed: 0.1,
  balance_kwh: 20,
  relay_status: true,
  signal_strength: 80,
  device_status: "ONLINE" as const,
  firmware_version: "1.0.0",
};

describe("telemetry validation", () => {
  it("accepts a physically coherent payload", () => {
    expect(telemetrySchema.parse(payload).meter_id).toBe("VSE-000001");
  });

  it("rejects a duplicate message_id", () => {
    const unique = {
      ...payload,
      message_id: "c6f0d190-ea75-46fc-9f08-8f17e0d4a9b1",
      device_timestamp: new Date().toISOString(),
    };
    ingestTelemetry(unique);
    expect(() => ingestTelemetry(unique)).toThrow(
      "message_id already processed"
    );
  });

  it("verifies HMAC signatures without trusting the client", () => {
    const signature = signTelemetryPayload(payload, "test-secret");
    expect(verifyTelemetrySignature(payload, signature, "test-secret")).toBe(
      true
    );
    expect(
      verifyTelemetrySignature(
        { ...payload, power: 441 },
        signature,
        "test-secret"
      )
    ).toBe(false);
  });

  it("validates the configured IoT secret when present", () => {
    const secret = process.env.VIRUNGA_IOT_HMAC_SECRET;
    if (!secret) return;
    const signature = signTelemetryPayload(payload, secret);
    expect(verifyTelemetrySignature(payload, signature, secret)).toBe(true);
  });

  it("rejects reuse of a valid manual recharge token", () => {
    const token = signToken("VSE-000001", 2026081501, 3, "meter-secret");
    expect(verifyToken(token, "VSE-000001", "meter-secret")).toBe(true);
    expect(verifyToken(token, "VSE-000001", "meter-secret")).toBe(false);
  });

  it("detects the requested anomaly categories", () => {
    const anomalies = detectAnomalies(
      {
        ...payload,
        voltage: 260,
        power: 6000,
        balance_kwh: 3,
        device_status: "OFFLINE",
      },
      { ...payload, device_timestamp: "2026-08-15T08:57:00.000Z" }
    );
    expect(anomalies.map(item => item.id)).toEqual(
      expect.arrayContaining([
        "ANOM-SURTENSION",
        "ANOM-SURCONSOMMATION",
        "ANOM-BALANCE",
        "ANOM-OFFLINE",
        "ANOM-HEARTBEAT",
      ])
    );
  });
});
