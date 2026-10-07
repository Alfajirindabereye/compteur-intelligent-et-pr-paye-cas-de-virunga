import { createHmac, timingSafeEqual } from "node:crypto";
import { z } from "zod";

export const rechargeSourceSchema = z.enum(["APP_PAIEMENT", "SAISIE_MANUELLE"]);
export type RechargeSource = z.infer<typeof rechargeSourceSchema>;

export const telemetrySchema = z.object({
  message_id: z.string().uuid(),
  meter_id: z.string().regex(/^VSE-\d{6}$/),
  device_timestamp: z.string().datetime({ offset: true }),
  voltage: z.number().finite().min(0).max(300),
  current: z.number().finite().min(0).max(100),
  power: z.number().finite().min(0).max(30000),
  energy_consumed: z.number().finite().min(0).max(100000),
  balance_kwh: z.number().finite().min(0).max(100000),
  relay_status: z.boolean(),
  signal_strength: z.number().int().min(0).max(100),
  device_status: z.enum(["ONLINE", "OFFLINE"]),
  firmware_version: z.string().min(1).max(32),
});
export type TelemetryPayload = z.infer<typeof telemetrySchema>;

export type TelemetryRecord = TelemetryPayload & {
  received_at: string;
};

export type Recharge = {
  id: string;
  meter_id: string;
  source: RechargeSource;
  amount_cdf: number;
  amount_usd: number;
  energy_kwh: number;
  status: "APPLIED" | "PENDING";
  applied_at: string;
  synced_at: string;
};

export type EnergySnapshot = {
  meter: {
    id: string;
    sector: string;
    location: string;
    device_status: "ONLINE" | "OFFLINE";
    relay_status: boolean;
    signal_strength: number;
    firmware_version: string;
  };
  telemetry: TelemetryRecord;
  balance: { kwh: number; cdf: number; usd: number };
  estimate_hours: number;
  budget: { limit_kwh: number; used_kwh: number; percentage: number };
  alerts: {
    id: string;
    severity: "INFO" | "WARNING" | "CRITICAL";
    title: string;
    detail: string;
  }[];
  consumption: { label: string; kwh: number; recharge?: RechargeSource }[];
  recharges: Recharge[];
};

const now = new Date();
const telemetry: TelemetryRecord = {
  message_id: "5c72b9c8-0fd3-4a62-9c91-1fbf2e20d114",
  meter_id: "VSE-000001",
  device_timestamp: new Date(now.getTime() - 3_000).toISOString(),
  voltage: 220.4,
  current: 2.31,
  power: 508.2,
  energy_consumed: 0.084,
  balance_kwh: 18.42,
  relay_status: true,
  signal_strength: 76,
  device_status: "ONLINE",
  firmware_version: "1.0.0",
  received_at: now.toISOString(),
};

const recharges: Recharge[] = [
  {
    id: "RCH-20260815-001",
    meter_id: "VSE-000001",
    source: "APP_PAIEMENT",
    amount_cdf: 25000,
    amount_usd: 8.62,
    energy_kwh: 10,
    status: "APPLIED",
    applied_at: new Date(now.getTime() - 86_400_000 * 2).toISOString(),
    synced_at: new Date(now.getTime() - 86_400_000 * 2 + 4_000).toISOString(),
  },
  {
    id: "RCH-20260815-002",
    meter_id: "VSE-000001",
    source: "SAISIE_MANUELLE",
    amount_cdf: 12500,
    amount_usd: 4.31,
    energy_kwh: 5,
    status: "APPLIED",
    applied_at: new Date(now.getTime() - 86_400_000).toISOString(),
    synced_at: new Date(now.getTime() - 86_400_000 + 21_600_000).toISOString(),
  },
];

const seenMessageIds = new Set([telemetry.message_id]);
const usedTokenDigests = new Set<string>();

export function buildSnapshot(): EnergySnapshot {
  const averagePowerKw = Math.max(telemetry.power / 1000, 0.05);
  const estimateHours =
    Math.round((telemetry.balance_kwh / averagePowerKw) * 10) / 10;
  const budgetUsed = 42.8;
  const computedAlerts = detectAnomalies(telemetry);
  if (budgetUsed > 40) {
    computedAlerts.push({
      id: "ANOM-BUDGET",
      severity: "WARNING",
      title: "Plafond de consommation dépassé",
      detail: `Consommation : ${budgetUsed.toFixed(1)} kWh pour une limite de 40 kWh.`,
    });
  }
  return {
    meter: {
      id: telemetry.meter_id,
      sector: "Goma — Karisimbi",
      location: "Quartier Himbi",
      device_status: telemetry.device_status,
      relay_status: telemetry.relay_status,
      signal_strength: telemetry.signal_strength,
      firmware_version: telemetry.firmware_version,
    },
    telemetry,
    balance: {
      kwh: telemetry.balance_kwh,
      cdf: Math.round(telemetry.balance_kwh * 2500),
      usd: Math.round(telemetry.balance_kwh * 1.15 * 100) / 100,
    },
    estimate_hours: estimateHours,
    budget: {
      limit_kwh: 40,
      used_kwh: budgetUsed,
      percentage: Math.round((budgetUsed / 40) * 100),
    },
    alerts:
      computedAlerts.length > 0
        ? computedAlerts
        : [
            {
              id: "ALT-001",
              severity: "INFO",
              title: "Compteur connecté",
              detail: "Dernier heartbeat reçu il y a moins de 5 secondes.",
            },
          ],
    consumption: [
      { label: "06:00", kwh: 0.42 },
      { label: "09:00", kwh: 0.86 },
      { label: "12:00", kwh: 0.68 },
      { label: "15:00", kwh: 0.92, recharge: "APP_PAIEMENT" },
      { label: "18:00", kwh: 1.32 },
      { label: "21:00", kwh: 1.74, recharge: "SAISIE_MANUELLE" },
      { label: "00:00", kwh: 1.05 },
    ],
    recharges: [...recharges],
  };
}

export function signTelemetryPayload(
  payload: TelemetryPayload,
  secret: string
) {
  return createHmac("sha256", secret)
    .update(JSON.stringify(payload))
    .digest("hex");
}

export function verifyTelemetrySignature(
  payload: TelemetryPayload,
  signature: string,
  secret: string
) {
  const expected = Buffer.from(signTelemetryPayload(payload, secret), "hex");
  const received = Buffer.from(signature, "hex");
  return (
    expected.length === received.length && timingSafeEqual(expected, received)
  );
}

export function detectAnomalies(
  current: TelemetryPayload,
  previous?: TelemetryPayload
) {
  const alerts: EnergySnapshot["alerts"] = [];
  if (current.voltage > 245)
    alerts.push({
      id: "ANOM-SURTENSION",
      severity: "CRITICAL",
      title: "Surtension détectée",
      detail: `Tension mesurée : ${current.voltage} V.`,
    });
  if (current.voltage < 180)
    alerts.push({
      id: "ANOM-SOUS-TENSION",
      severity: "WARNING",
      title: "Sous-tension détectée",
      detail: `Tension mesurée : ${current.voltage} V.`,
    });
  if (current.device_status === "OFFLINE")
    alerts.push({
      id: "ANOM-OFFLINE",
      severity: "CRITICAL",
      title: "Perte de communication",
      detail: "Le compteur est déclaré hors ligne.",
    });
  if (current.power > 5000)
    alerts.push({
      id: "ANOM-SURCONSOMMATION",
      severity: "WARNING",
      title: "Surconsommation détectée",
      detail: `Puissance mesurée : ${current.power} W.`,
    });
  if (
    previous &&
    Date.parse(current.device_timestamp) -
      Date.parse(previous.device_timestamp) >
      90_000
  )
    alerts.push({
      id: "ANOM-HEARTBEAT",
      severity: "WARNING",
      title: "Heartbeat en retard",
      detail: "L’intervalle entre deux messages dépasse 90 secondes.",
    });
  if (current.balance_kwh <= 5)
    alerts.push({
      id: "ANOM-BALANCE",
      severity: "WARNING",
      title: "Solde bas",
      detail: `Solde restant : ${current.balance_kwh} kWh.`,
    });
  return alerts;
}

export function ingestTelemetry(payload: unknown) {
  const parsed = telemetrySchema.parse(payload);
  const deviceTime = Date.parse(parsed.device_timestamp);
  if (deviceTime > Date.now() + 60_000)
    throw new Error("device_timestamp is in the future");
  if (Date.now() - deviceTime > 24 * 60 * 60 * 1000)
    throw new Error("device_timestamp is too old");
  if (deviceTime < Date.parse(telemetry.device_timestamp) - 60_000)
    throw new Error("device_timestamp is out of order");
  if (seenMessageIds.has(parsed.message_id))
    throw new Error("message_id already processed");
  const powerTolerance = Math.max(80, parsed.voltage * parsed.current * 0.35);
  if (Math.abs(parsed.power - parsed.voltage * parsed.current) > powerTolerance)
    throw new Error("power is inconsistent with voltage and current");
  seenMessageIds.add(parsed.message_id);
  Object.assign(telemetry, parsed, { received_at: new Date().toISOString() });
  return telemetry;
}

export function createRechargeReceiptPdf(rechargeId: string) {
  const recharge = recharges.find(item => item.id === rechargeId);
  if (!recharge) throw new Error("Recharge introuvable");
  const lines = [
    "Virunga Smart Energy — Recu de recharge",
    `Recharge: ${recharge.id}`,
    `Compteur: ${recharge.meter_id}`,
    `Source: ${recharge.source}`,
    `Energie: ${recharge.energy_kwh.toFixed(2)} kWh`,
    `Montant: ${recharge.amount_cdf.toFixed(0)} CDF / ${recharge.amount_usd.toFixed(2)} USD`,
    `applied_at: ${recharge.applied_at}`,
    `synced_at: ${recharge.synced_at}`,
    "DEMO — simulation academique independante",
  ];
  const escape = (text: string) =>
    text.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
  const stream = [
    "BT",
    "/F1 12 Tf",
    "50 760 Td",
    ...lines.map(
      (line, index) => `${index ? "0 -24 Td" : ""} (${escape(line)}) Tj`
    ),
    "ET",
  ].join(" ");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${stream.length} >>\\nstream\\n${stream}\\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\\n";
  const offsets = [0];
  for (let index = 0; index < objects.length; index++) {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\\n${objects[index]}\\nendobj\\n`;
  }
  const xref = pdf.length;
  pdf += `xref\\n0 ${objects.length + 1}\\n0000000000 65535 f \\n`;
  for (let index = 1; index < offsets.length; index++)
    pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \\n`;
  pdf += `trailer\\n<< /Size ${objects.length + 1} /Root 1 0 R >>\\nstartxref\\n${xref}\\n%%EOF`;
  return Buffer.from(pdf, "utf8").toString("base64");
}

export function signToken(
  meterId: string,
  sequence: number,
  energyKwh: number,
  secret: string
) {
  const body = `${meterId}:${sequence}:${energyKwh.toFixed(3)}`;
  return `${body}:${createHmac("sha256", secret).update(body).digest("hex")}`;
}

export function getTokenDigest(token: string) {
  return createHmac("sha256", "token-digest").update(token).digest("hex");
}

export function verifyToken(token: string, meterId: string, secret: string) {
  const parts = token.split(":");
  if (parts.length !== 4 || parts[0] !== meterId) return false;
  const body = parts.slice(0, 3).join(":");
  const expected = createHmac("sha256", secret).update(body).digest("hex");
  const provided = Buffer.from(parts[3], "hex");
  const actual = Buffer.from(expected, "hex");
  const valid =
    provided.length === actual.length && timingSafeEqual(provided, actual);
  if (!valid) return false;
  const digest = getTokenDigest(token);
  if (usedTokenDigests.has(digest)) return false;
  usedTokenDigests.add(digest);
  return true;
}
