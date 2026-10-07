import { desc, eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import {
  InsertUser,
  alerts,
  broadcastMessages,
  budgetSettings,
  meterTokens,
  meters,
  paymentEvents,
  recharges,
  sectors,
  telemetry,
  users,
} from "../drizzle/schema";
import { ENV } from "./_core/env";

let _db: ReturnType<typeof drizzle> | null = null;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) {
    throw new Error("User openId is required for upsert");
  }

  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot upsert user: database not available");
    return;
  }

  try {
    const values: InsertUser = {
      openId: user.openId,
    };
    const updateSet: Record<string, unknown> = {};

    const textFields = ["name", "email", "loginMethod"] as const;
    type TextField = (typeof textFields)[number];

    const assignNullable = (field: TextField) => {
      const value = user[field];
      if (value === undefined) return;
      const normalized = value ?? null;
      values[field] = normalized;
      updateSet[field] = normalized;
    };

    textFields.forEach(assignNullable);

    if (user.lastSignedIn !== undefined) {
      values.lastSignedIn = user.lastSignedIn;
      updateSet.lastSignedIn = user.lastSignedIn;
    }
    if (user.role !== undefined) {
      values.role = user.role;
      updateSet.role = user.role;
    } else if (user.openId === ENV.ownerOpenId) {
      values.role = "admin";
      updateSet.role = "admin";
      values.domainRole = "administrateur";
      updateSet.domainRole = "administrateur";
    }

    if (!values.lastSignedIn) {
      values.lastSignedIn = new Date();
    }

    if (Object.keys(updateSet).length === 0) {
      updateSet.lastSignedIn = new Date();
    }

    await db.insert(users).values(values).onDuplicateKeyUpdate({
      set: updateSet,
    });
  } catch (error) {
    console.error("[Database] Failed to upsert user:", error);
    throw error;
  }
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot get user: database not available");
    return undefined;
  }

  const result = await db
    .select()
    .from(users)
    .where(eq(users.openId, openId))
    .limit(1);

  return result.length > 0 ? result[0] : undefined;
}

export async function saveBroadcastDraft(input: {
  rawInformation: string;
  generatedMessage: string;
  status: "DRAFT" | "PUBLISHED";
  createdBy: number;
}) {
  const db = await getDb();
  if (!db) return undefined;
  const id = `BCAST-${Date.now()}`;
  await db.insert(broadcastMessages).values({
    id,
    rawInformation: input.rawInformation,
    generatedMessage: input.generatedMessage,
    status: input.status,
    createdBy: input.createdBy,
  });
  return id;
}

export async function publishBroadcast(id: string) {
  const db = await getDb();
  if (!db) return false;
  await db
    .update(broadcastMessages)
    .set({ status: "PUBLISHED" })
    .where(eq(broadcastMessages.id, id));
  return true;
}

export async function getSectorOverview() {
  const db = await getDb();
  if (!db) return undefined;
  const [sectorRows, rows] = await Promise.all([
    db.select({ name: sectors.name }).from(sectors),
    db
      .select({ sector: meters.sector, deviceStatus: meters.deviceStatus })
      .from(meters),
  ]);
  const grouped = new Map<
    string,
    { name: string; online: number; offline: number }
  >(
    sectorRows.map(sector => [
      sector.name,
      { name: sector.name, online: 0, offline: 0 },
    ])
  );
  for (const row of rows) {
    const entry = grouped.get(row.sector) ?? {
      name: row.sector,
      online: 0,
      offline: 0,
    };
    row.deviceStatus === "ONLINE" ? entry.online++ : entry.offline++;
    grouped.set(row.sector, entry);
  }
  return Array.from(grouped.values());
}

export async function getMeterContextByOwnerOpenId(ownerOpenId: string) {
  const db = await getDb();
  if (!db) return undefined;
  const meter = (
    await db
      .select()
      .from(meters)
      .where(eq(meters.ownerOpenId, ownerOpenId))
      .limit(1)
  )[0];
  if (!meter) return undefined;
  const [latestTelemetry, rechargeHistory, meterAlerts] = await Promise.all([
    db
      .select()
      .from(telemetry)
      .where(eq(telemetry.meterId, meter.id))
      .orderBy(desc(telemetry.deviceTimestamp))
      .limit(10),
    db
      .select()
      .from(recharges)
      .where(eq(recharges.meterId, meter.id))
      .orderBy(desc(recharges.appliedAt))
      .limit(20),
    db
      .select()
      .from(alerts)
      .where(eq(alerts.meterId, meter.id))
      .orderBy(desc(alerts.createdAt))
      .limit(20),
  ]);
  return {
    meter,
    telemetry: latestTelemetry,
    recharges: rechargeHistory,
    alerts: meterAlerts,
  };
}

export async function applyManualRecharge(input: {
  tokenDigest: string;
  meterId: string;
  sequence: number;
  energyKwh: number;
  amountCdf: number;
  amountUsd: number;
  appliedAt: Date;
  syncedAt: Date;
}) {
  const db = await getDb();
  if (!db) return false;
  const current = await db
    .select()
    .from(meters)
    .where(eq(meters.id, input.meterId))
    .limit(1);
  if (!current[0]) throw new Error("Compteur introuvable en base.");
  await db.insert(meterTokens).values({
    meterId: input.meterId,
    sequence: input.sequence,
    tokenDigest: input.tokenDigest,
    energyKwh: String(input.energyKwh),
    appliedAt: input.appliedAt,
    syncedAt: input.syncedAt,
    used: 1,
  });
  await db.insert(recharges).values({
    id: `MAN-${input.tokenDigest.slice(0, 24)}`,
    meterId: input.meterId,
    source: "SAISIE_MANUELLE",
    status: "APPLIED",
    amountCdf: String(input.amountCdf),
    amountUsd: String(input.amountUsd),
    energyKwh: String(input.energyKwh),
    appliedAt: input.appliedAt,
    syncedAt: input.syncedAt,
  });
  const balance = Number(current[0].balanceKwh) + input.energyKwh;
  await db
    .update(meters)
    .set({ balanceKwh: String(balance), relayStatus: balance > 0 ? 1 : 0 })
    .where(eq(meters.id, input.meterId));
  return true;
}

export async function recordPaymentEvent(event: {
  id: string;
  provider: string;
  status: string;
  payload: unknown;
}) {
  const db = await getDb();
  if (!db) return false;
  await db
    .insert(paymentEvents)
    .values({
      id: event.id,
      provider: event.provider,
      status: event.status,
      payload: JSON.stringify(event.payload),
    })
    .onDuplicateKeyUpdate({
      set: { status: event.status, payload: JSON.stringify(event.payload) },
    });
  return true;
}

export async function recordTelemetry(payload: {
  message_id: string;
  meter_id: string;
  device_timestamp: string;
  received_at: string;
  voltage: number;
  current: number;
  power: number;
  energy_consumed: number;
  balance_kwh: number;
  relay_status: boolean;
  signal_strength: number;
  device_status: "ONLINE" | "OFFLINE";
  firmware_version: string;
}) {
  const db = await getDb();
  if (!db) return false;
  await db.insert(telemetry).values({
    messageId: payload.message_id,
    meterId: payload.meter_id,
    deviceTimestamp: new Date(payload.device_timestamp),
    receivedAt: new Date(payload.received_at),
    voltage: String(payload.voltage),
    current: String(payload.current),
    power: String(payload.power),
    energyConsumed: String(payload.energy_consumed),
    balanceKwh: String(payload.balance_kwh),
    relayStatus: payload.relay_status ? 1 : 0,
    signalStrength: payload.signal_strength,
    deviceStatus: payload.device_status,
    firmwareVersion: payload.firmware_version,
  });
  await db
    .update(meters)
    .set({ relayStatus: payload.balance_kwh > 0 ? 1 : 0 })
    .where(eq(meters.id, payload.meter_id));
  const budget = (
    await db
      .select()
      .from(budgetSettings)
      .where(eq(budgetSettings.meterId, payload.meter_id))
      .limit(1)
  )[0];
  if (
    budget &&
    payload.energy_consumed >=
      Number(budget.limitKwh) * (Number(budget.warningPercentage) / 100)
  ) {
    await db.insert(alerts).values({
      id: `BUDGET-${payload.message_id}`,
      meterId: payload.meter_id,
      severity: "WARNING",
      type: "BUDGET",
      title: "Plafond de consommation approché",
      detail: `Consommation ${payload.energy_consumed} kWh sur une limite de ${budget.limitKwh} kWh.`,
      createdAt: new Date(),
    });
  }
  return true;
}
