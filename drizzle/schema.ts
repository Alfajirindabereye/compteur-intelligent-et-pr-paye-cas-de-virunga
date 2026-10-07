import {
  decimal,
  int,
  mysqlEnum,
  mysqlTable,
  text,
  timestamp,
  varchar,
} from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  /**
   * Surrogate primary key. Auto-incremented numeric value managed by the database.
   * Use this for relations between tables.
   */
  id: int("id").autoincrement().primaryKey(),
  /** Manus OAuth identifier (openId) returned from the OAuth callback. Unique per user. */
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  domainRole: mysqlEnum("domainRole", ["abonne", "administrateur"])
    .default("abonne")
    .notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

export const meters = mysqlTable("meters", {
  id: varchar("id", { length: 32 }).primaryKey(),
  ownerOpenId: varchar("ownerOpenId", { length: 64 }),
  sector: varchar("sector", { length: 128 }).notNull(),
  location: varchar("location", { length: 255 }).notNull(),
  deviceStatus: mysqlEnum("deviceStatus", ["ONLINE", "OFFLINE"])
    .default("OFFLINE")
    .notNull(),
  relayStatus: int("relayStatus").default(0).notNull(),
  signalStrength: int("signalStrength").default(0).notNull(),
  firmwareVersion: varchar("firmwareVersion", { length: 32 }).notNull(),
  balanceKwh: decimal("balanceKwh", { precision: 12, scale: 3 })
    .default("0")
    .notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export const telemetry = mysqlTable("telemetry", {
  id: int("id").autoincrement().primaryKey(),
  messageId: varchar("messageId", { length: 64 }).notNull().unique(),
  meterId: varchar("meterId", { length: 32 }).notNull(),
  deviceTimestamp: timestamp("deviceTimestamp").notNull(),
  receivedAt: timestamp("receivedAt").defaultNow().notNull(),
  voltage: decimal("voltage", { precision: 10, scale: 3 }).notNull(),
  current: decimal("current", { precision: 10, scale: 3 }).notNull(),
  power: decimal("power", { precision: 12, scale: 3 }).notNull(),
  energyConsumed: decimal("energyConsumed", {
    precision: 12,
    scale: 3,
  }).notNull(),
  balanceKwh: decimal("balanceKwh", { precision: 12, scale: 3 }).notNull(),
  relayStatus: int("relayStatus").notNull(),
  signalStrength: int("signalStrength").notNull(),
  deviceStatus: mysqlEnum("deviceStatus", ["ONLINE", "OFFLINE"]).notNull(),
  firmwareVersion: varchar("firmwareVersion", { length: 32 }).notNull(),
});

export const recharges = mysqlTable("recharges", {
  id: varchar("id", { length: 64 }).primaryKey(),
  meterId: varchar("meterId", { length: 32 }).notNull(),
  source: mysqlEnum("source", ["APP_PAIEMENT", "SAISIE_MANUELLE"]).notNull(),
  status: mysqlEnum("status", ["APPLIED", "PENDING"]).notNull(),
  amountCdf: decimal("amountCdf", { precision: 14, scale: 2 }).notNull(),
  amountUsd: decimal("amountUsd", { precision: 14, scale: 2 }).notNull(),
  energyKwh: decimal("energyKwh", { precision: 12, scale: 3 }).notNull(),
  appliedAt: timestamp("appliedAt").notNull(),
  syncedAt: timestamp("syncedAt").notNull(),
  providerReference: varchar("providerReference", { length: 128 }),
});

export const alerts = mysqlTable("alerts", {
  id: varchar("id", { length: 64 }).primaryKey(),
  meterId: varchar("meterId", { length: 32 }).notNull(),
  severity: mysqlEnum("severity", ["INFO", "WARNING", "CRITICAL"]).notNull(),
  type: varchar("type", { length: 64 }).notNull(),
  title: varchar("title", { length: 255 }).notNull(),
  detail: text("detail").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  acknowledgedAt: timestamp("acknowledgedAt"),
});

export const sectors = mysqlTable("sectors", {
  id: varchar("id", { length: 32 }).primaryKey(),
  name: varchar("name", { length: 128 }).notNull().unique(),
  territory: varchar("territory", { length: 128 }).notNull(),
});

export const budgetSettings = mysqlTable("budgetSettings", {
  meterId: varchar("meterId", { length: 32 }).primaryKey(),
  limitKwh: decimal("limitKwh", { precision: 12, scale: 3 }).notNull(),
  warningPercentage: int("warningPercentage").default(80).notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export const meterTokens = mysqlTable("meterTokens", {
  id: int("id").autoincrement().primaryKey(),
  meterId: varchar("meterId", { length: 32 }).notNull(),
  sequence: int("sequence").notNull(),
  tokenDigest: varchar("tokenDigest", { length: 128 }).notNull().unique(),
  energyKwh: decimal("energyKwh", { precision: 12, scale: 3 }).notNull(),
  appliedAt: timestamp("appliedAt"),
  syncedAt: timestamp("syncedAt"),
  used: int("used").default(0).notNull(),
});

export const paymentEvents = mysqlTable("paymentEvents", {
  id: varchar("id", { length: 128 }).primaryKey(),
  provider: varchar("provider", { length: 32 }).notNull(),
  status: varchar("status", { length: 32 }).notNull(),
  payload: text("payload").notNull(),
  receivedAt: timestamp("receivedAt").defaultNow().notNull(),
});

export const broadcastMessages = mysqlTable("broadcastMessages", {
  id: varchar("id", { length: 64 }).primaryKey(),
  rawInformation: text("rawInformation").notNull(),
  generatedMessage: text("generatedMessage").notNull(),
  status: mysqlEnum("status", ["DRAFT", "PUBLISHED"]).notNull(),
  createdBy: int("createdBy").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  publishedAt: timestamp("publishedAt"),
});
