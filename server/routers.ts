import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { protectedProcedure, publicProcedure, router } from "./_core/trpc";
import { invokeLLM } from "./_core/llm";
import {
  issueAccessToken,
  issueRefreshToken,
  verifyRefreshToken,
} from "./authTokens";
import {
  applyManualRecharge,
  getMeterContextByOwnerOpenId,
  getSectorOverview,
  publishBroadcast,
  recordTelemetry,
  saveBroadcastDraft,
} from "./db";
import { startFlutterwaveCheckout, startPawaPayDeposit } from "./payments";
import {
  buildSnapshot,
  createRechargeReceiptPdf,
  detectAnomalies,
  getTokenDigest,
  ingestTelemetry,
  signTelemetryPayload,
  signToken,
  telemetrySchema,
  verifyTelemetrySignature,
  verifyToken,
} from "./energy";

const adminProcedure = protectedProcedure.use(({ ctx, next }) => {
  if (ctx.user.role !== "admin" && ctx.user.domainRole !== "administrateur") {
    throw new TRPCError({
      code: "FORBIDDEN",
      message: "Accès administrateur requis.",
    });
  }
  return next();
});

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(opts => opts.ctx.user),
    tokens: protectedProcedure.query(async ({ ctx }) => ({
      accessToken: await issueAccessToken(ctx.user),
      refreshToken: await issueRefreshToken(ctx.user),
      tokenType: "Bearer" as const,
    })),
    refresh: publicProcedure
      .input(z.object({ refreshToken: z.string().min(20) }))
      .mutation(async ({ input }) => {
        try {
          const payload = await verifyRefreshToken(input.refreshToken);
          return {
            accessToken: await issueAccessToken({
              id: Number(payload.sub),
              openId: String(payload.openId),
              role: String(payload.role),
            }),
            tokenType: "Bearer" as const,
          };
        } catch {
          throw new TRPCError({
            code: "UNAUTHORIZED",
            message: "Refresh token invalide ou expiré.",
          });
        }
      }),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),
  payments: router({
    pawaPayDeposit: protectedProcedure
      .input(
        z.object({
          amount: z.string().regex(/^\d+(\.\d{1,2})?$/),
          currency: z.enum(["CDF", "USD"]),
          provider: z.enum(["VODACOM_MPESA_COD", "AIRTEL_COD", "ORANGE_COD"]),
          phoneNumber: z.string().min(8).max(20),
        })
      )
      .mutation(async ({ input }) => {
        try {
          return await startPawaPayDeposit({
            ...input,
            statementDescription: "Virunga Smart Energy",
          });
        } catch (error) {
          throw new TRPCError({
            code: "BAD_GATEWAY",
            message:
              error instanceof Error ? error.message : "PawaPay indisponible.",
          });
        }
      }),
    flutterwaveCheckout: protectedProcedure
      .input(
        z.object({
          amount: z.number().positive(),
          currency: z.enum(["CDF", "USD"]),
          email: z.string().email(),
          name: z.string().optional(),
          phoneNumber: z.string().optional(),
          redirectUrl: z.string().url(),
        })
      )
      .mutation(async ({ input }) => {
        try {
          return await startFlutterwaveCheckout(input);
        } catch (error) {
          throw new TRPCError({
            code: "BAD_GATEWAY",
            message:
              error instanceof Error
                ? error.message
                : "Flutterwave indisponible.",
          });
        }
      }),
  }),
  energy: router({
    dashboard: publicProcedure.query(() => buildSnapshot()),
    adminOverview: adminProcedure.query(async () => {
      const snapshot = buildSnapshot();
      const persistedSectors = await getSectorOverview();
      return {
        sectors: persistedSectors?.length
          ? persistedSectors
          : [
              { name: "Goma — Karisimbi", online: 18, offline: 2 },
              { name: "Rutshuru — Matebe", online: 11, offline: 1 },
            ],
        totalMeters: 32,
        onlineMeters: 29,
        lowBalanceMeters: 6,
        snapshot,
      };
    }),
    ingest: adminProcedure
      .input(
        z.object({
          payload: telemetrySchema,
          signature: z.string().regex(/^[a-f0-9]{64}$/),
        })
      )
      .mutation(async ({ input }) => {
        try {
          const secret = process.env.VIRUNGA_IOT_HMAC_SECRET;
          if (
            !secret ||
            !verifyTelemetrySignature(input.payload, input.signature, secret)
          )
            throw new Error("signature HMAC absente ou invalide");
          const accepted = ingestTelemetry(input.payload);
          await recordTelemetry(accepted);
          return {
            accepted: true,
            telemetry: accepted,
            anomalies: detectAnomalies(input.payload),
          };
        } catch (error) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message:
              error instanceof Error
                ? error.message
                : "Payload rejeté et journalisé.",
          });
        }
      }),
    simulate: adminProcedure.mutation(() => {
      const snapshot = buildSnapshot();
      const payload = {
        ...snapshot.telemetry,
        message_id: crypto.randomUUID(),
        device_timestamp: new Date().toISOString(),
        voltage: Math.round((218 + Math.random() * 5) * 10) / 10,
        current: Math.round((1.8 + Math.random() * 1.2) * 100) / 100,
        power: 0,
      };
      payload.power = Math.round(payload.voltage * payload.current * 100) / 100;
      const secret = process.env.VIRUNGA_IOT_HMAC_SECRET;
      const signature = secret ? signTelemetryPayload(payload, secret) : null;
      return {
        accepted: true,
        telemetry: ingestTelemetry(payload),
        signature,
        anomalies: detectAnomalies(payload),
      };
    }),
    manualRecharge: protectedProcedure
      .input(
        z.object({
          token: z.string().min(20),
          energyKwh: z.number().positive().max(1000),
        })
      )
      .mutation(async ({ input }) => {
        const secret = process.env.VIRUNGA_METER_HMAC_SECRET;
        if (!secret)
          throw new TRPCError({
            code: "PRECONDITION_FAILED",
            message:
              "VIRUNGA_METER_HMAC_SECRET n’est pas configuré : la validation HMAC réelle est donc bloquée.",
          });
        const snapshot = buildSnapshot();
        if (!verifyToken(input.token, snapshot.meter.id, secret))
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Token invalide, mal signé ou réutilisé.",
          });
        const syncedAt = new Date();
        const appliedAt = new Date(syncedAt.getTime() - 1000);
        const sequence = Number(input.token.split(":")[1]);
        await applyManualRecharge({
          tokenDigest: getTokenDigest(input.token),
          meterId: snapshot.meter.id,
          sequence,
          energyKwh: input.energyKwh,
          amountCdf: Math.round(input.energyKwh * 2500),
          amountUsd: Math.round(input.energyKwh * 1.15 * 100) / 100,
          appliedAt,
          syncedAt,
        });
        return {
          accepted: true,
          source: "SAISIE_MANUELLE" as const,
          applied_at: appliedAt.toISOString(),
          synced_at: syncedAt.toISOString(),
        };
      }),
    receipt: protectedProcedure
      .input(z.object({ rechargeId: z.string().min(1) }))
      .mutation(({ input }) => {
        try {
          return {
            filename: `${input.rechargeId}.pdf`,
            base64: createRechargeReceiptPdf(input.rechargeId),
          };
        } catch (error) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message:
              error instanceof Error ? error.message : "Reçu indisponible.",
          });
        }
      }),
    aiAssistant: protectedProcedure
      .input(z.object({ question: z.string().min(2).max(500) }))
      .mutation(async ({ ctx, input }) => {
        const assignedMeter = await getMeterContextByOwnerOpenId(
          ctx.user.openId
        );
        if (!assignedMeter)
          return {
            answer:
              "Aucun compteur réel n’est associé à votre compte. Les données DEMO visibles dans le tableau ne peuvent pas être utilisées pour une réponse personnalisée.",
          };
        const response = await invokeLLM({
          messages: [
            {
              role: "system",
              content:
                "Tu es l’agent IA de Virunga Smart Energy. Réponds en français, avec des conseils prudents et uniquement à partir des données fournies. Si la donnée manque, dis explicitement qu’elle n’est pas disponible. Ne prétends jamais contrôler le relais ou confirmer un paiement.",
            },
            {
              role: "user",
              content: JSON.stringify({
                question: input.question,
                compteur: assignedMeter.meter,
                telemetrie: assignedMeter.telemetry,
                solde_et_historique: assignedMeter.recharges,
                alertes: assignedMeter.alerts,
                source: "DONNEES_PERSISTEES_COMPTEUR",
                instruction:
                  "Répondre uniquement à partir de cet enregistrement réel. Signaler toute métrique absente.",
              }),
            },
          ],
        });
        const content = response.choices?.[0]?.message?.content;
        return {
          answer:
            typeof content === "string"
              ? content
              : "Aucune réponse exploitable n’a été produite.",
        };
      }),
    broadcastDraft: adminProcedure
      .input(z.object({ rawInformation: z.string().min(5).max(1000) }))
      .mutation(async ({ ctx, input }) => {
        const response = await invokeLLM({
          messages: [
            {
              role: "system",
              content:
                "Rédige un message de diffusion court, factuel et neutre pour des abonnés d’un réseau électrique. N’invente aucune date, durée, secteur ou cause absente de l’information brute. Retourne uniquement le message final.",
            },
            { role: "user", content: input.rawInformation },
          ],
        });
        const content = response.choices?.[0]?.message?.content;
        const message =
          typeof content === "string" ? content : input.rawInformation;
        const id = await saveBroadcastDraft({
          rawInformation: input.rawInformation,
          generatedMessage: message,
          status: "DRAFT",
          createdBy: ctx.user.id,
        });
        return { id, status: "DRAFT" as const, message };
      }),
    publishBroadcast: adminProcedure
      .input(z.object({ id: z.string().min(1) }))
      .mutation(async ({ input }) => ({
        id: input.id,
        status: (await publishBroadcast(input.id))
          ? ("PUBLISHED" as const)
          : ("UNAVAILABLE" as const),
      })),
    demoToken: adminProcedure
      .input(z.object({ energyKwh: z.number().positive().max(1000) }))
      .mutation(({ input }) => {
        const secret = process.env.VIRUNGA_METER_HMAC_SECRET;
        if (!secret)
          throw new TRPCError({
            code: "PRECONDITION_FAILED",
            message: "VIRUNGA_METER_HMAC_SECRET n’est pas configuré.",
          });
        return {
          token: signToken(
            buildSnapshot().meter.id,
            Date.now(),
            input.energyKwh,
            secret
          ),
          demo: true,
        };
      }),
  }),
});

export type AppRouter = typeof appRouter;
