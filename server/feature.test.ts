import { describe, expect, it } from "vitest";
import { appRouter } from "./routers";
import { buildSnapshot, createRechargeReceiptPdf } from "./energy";
import type { TrpcContext } from "./_core/context";

function context(role: "admin" | "user"): TrpcContext {
  return {
    user: {
      id: role === "admin" ? 1 : 2,
      openId: `feature-${role}`,
      email: `${role}@example.com`,
      name: role,
      loginMethod: "test",
      role,
      domainRole: role === "admin" ? "administrateur" : "abonne",
      createdAt: new Date(),
      updatedAt: new Date(),
      lastSignedIn: new Date(),
    },
    req: { protocol: "https", headers: {} } as TrpcContext["req"],
    res: {} as TrpcContext["res"],
  };
}

describe("Virunga feature contracts", () => {
  it("exposes calculated budget alerts and separate recharge timestamps", () => {
    const snapshot = buildSnapshot();
    expect(snapshot.alerts.some(alert => alert.id === "ANOM-BUDGET")).toBe(
      true
    );
    expect(
      snapshot.recharges.every(
        recharge => recharge.applied_at && recharge.synced_at
      )
    ).toBe(true);
  });

  it("generates a PDF for each known recharge id", () => {
    const snapshot = buildSnapshot();
    for (const recharge of snapshot.recharges) {
      expect(createRechargeReceiptPdf(recharge.id).startsWith("JVBERi0")).toBe(
        true
      );
    }
  });

  it("keeps admin overview behind the server role gate", async () => {
    const admin = appRouter.createCaller(context("admin"));
    const result = await admin.energy.adminOverview();
    expect(result.totalMeters).toBeGreaterThan(0);
    const user = appRouter.createCaller(context("user"));
    await expect(user.energy.adminOverview()).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
  });

  it("refuses AI personalization when no persisted meter is assigned", async () => {
    const user = appRouter.createCaller(context("user"));
    const result = await user.energy.aiAssistant({
      question: "Quel est mon solde ?",
    });
    expect(result.answer).toContain("Aucun compteur réel");
  });
});
