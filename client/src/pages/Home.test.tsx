import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Home from "./Home";

const dashboard = {
  mode: "DEMO",
  meter: { id: "VSF-000001", signal_strength: 86, device_status: "ONLINE", relay_status: true },
  telemetry: { voltage: 228.3, current: 2.15, power: 490, energy_consumed: 183.2 },
  balance: { kwh: 18.42, cdf: 18420, usd: 6.3 },
  budget: { limit_kwh: 40 },
  estimate_hours: 15.5,
  consumption: [
    { label: "08h", kwh: 1.2 },
    { label: "12h", kwh: 2.1, recharge: "APP_PAIEMENT" },
    { label: "16h", kwh: 1.6 },
  ],
  consumption_daily: [
    { label: "Nuit", kwh: 0.4 },
    { label: "Matin", kwh: 1.2 },
    { label: "Après-midi", kwh: 2.1 },
    { label: "Soirée", kwh: 1.2 },
  ],
  consumption_weekly: [
    { label: "Lundi", kwh: 1.1 },
    { label: "Mardi", kwh: 1.4 },
    { label: "Mercredi", kwh: 0.9 },
    { label: "Jeudi", kwh: 1.6 },
    { label: "Vendredi", kwh: 2.2 },
    { label: "Samedi", kwh: 1.8 },
    { label: "Dimanche", kwh: 1.3 },
  ],
  relay_command: null,
};

const mocks = vi.hoisted(() => ({
  loginSubscriber: vi.fn().mockResolvedValue({ accessToken: "subscriber-token", subscriber: { firstName: "Amani", lastName: "Kambale", meterId: "VSF-000001" } }),
  requestRelayCommand: vi.fn().mockResolvedValue({ id: 1, status: "PENDING", desired_state: "OFF" }),
}));

vi.mock("@/lib/djangoEnergy", () => ({
  clearSubscriberSession: vi.fn(),
  loginSubscriber: mocks.loginSubscriber,
  requestRelayCommand: mocks.requestRelayCommand,
  useDjangoDashboard: () => ({ data: { ...dashboard, relay_command: mocks.requestRelayCommand.mock.calls.length ? { id: 1, status: "PENDING", desired_state: "OFF" } : null }, isLoading: false, error: null }),
  useLocalNews: () => ({ data: [], isLoading: false, error: null }),
}));

afterEach(() => {
  cleanup();
  mocks.loginSubscriber.mockClear();
  mocks.requestRelayCommand.mockClear();
});

describe("public and subscriber UI", () => {
  it("opens the public login, validates the code and requests a Django subscriber session", async () => {
    const user = userEvent.setup();
    render(<Home />);

    expect(screen.getByRole("link", { name: "Accueil" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Espace Abonné/i }));
    await user.click(screen.getByRole("button", { name: /Accéder à mon espace sécurisé/i }));
    expect(screen.getByText("Code invalide.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Nom"), "Kambale");
    await user.type(screen.getByLabelText("Prénom"), "Amani");
    await user.type(screen.getByLabelText("Code du compteur"), "12345678901234567890");
    await user.click(screen.getByRole("button", { name: /Accéder à mon espace sécurisé/i }));

    expect(await screen.findByText("État du compteur et crédit prépayé")).toBeInTheDocument();
    expect(mocks.loginSubscriber).toHaveBeenCalledWith({ firstName: "Amani", lastName: "Kambale", meterCode: "12345678901234567890" });
  });

  it("requires confirmation then sends a pending relay command to Django", async () => {
    const user = userEvent.setup();
    render(<Home />);
    await user.click(screen.getByRole("button", { name: /Espace Abonné/i }));
    await user.type(screen.getByLabelText("Nom"), "Kambale");
    await user.type(screen.getByLabelText("Prénom"), "Amani");
    await user.type(screen.getByLabelText("Code du compteur"), "12345678901234567890");
    await user.click(screen.getByRole("button", { name: /Accéder à mon espace sécurisé/i }));

    await user.click(await screen.findByRole("button", { name: "Demander l’isolement" }));
    expect(screen.getByText("Confirmer la demande relais")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmer l’isolement" }));
    expect(mocks.requestRelayCommand).toHaveBeenCalledWith("subscriber-token", "OFF");
    expect(await screen.findByText(/COMMANDE EN ATTENTE/)).toBeInTheDocument();
  });

  it("renders the daily and weekly consumption donuts with totals", async () => {
    const user = userEvent.setup();
    render(<Home />);
    await user.click(screen.getByRole("button", { name: /Espace Abonné/i }));
    await user.type(screen.getByLabelText("Nom"), "Kambale");
    await user.type(screen.getByLabelText("Prénom"), "Amani");
    await user.type(screen.getByLabelText("Code du compteur"), "12345678901234567890");
    await user.click(screen.getByRole("button", { name: /Accéder à mon espace sécurisé/i }));

    expect(await screen.findByText("Consommation journalière")).toBeInTheDocument();
    expect(screen.getByText("Consommation hebdomadaire")).toBeInTheDocument();
    // Totaux au centre des camemberts : 4,9 kWh (journalier) et 10,3 kWh (hebdo)
    expect(screen.getByText("4,9 kWh")).toBeInTheDocument();
    expect(screen.getByText("10,3 kWh")).toBeInTheDocument();
    // Mention DEMO visible sur les cartes
    expect(screen.getAllByText("DONNÉES DEMO").length).toBeGreaterThanOrEqual(2);
    // Deux camemberts SVG rendus
    expect(screen.getAllByRole("img", { name: "Répartition de la consommation" })).toHaveLength(2);
  });
});
