import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Admin from "./Admin";

const overview = {
  totalMeters: 12,
  onlineMeters: 9,
  lowBalanceMeters: 2,
  openAlerts: 3,
  sectors: [{ name: "Goma — Karisimbi", territory: "Goma", online: 9, offline: 3, total: 12 }],
};

const mocks = vi.hoisted(() => ({
  token: null as string | null,
  loginAdmin: vi.fn(),
  getAdminOverview: vi.fn(),
  issueManualToken: vi.fn(),
}));

vi.mock("@/lib/djangoEnergy", () => ({
  getAdminToken: () => mocks.token,
  clearAdminSession: vi.fn(),
  loginAdmin: mocks.loginAdmin,
  getAdminOverview: mocks.getAdminOverview,
  issueManualToken: mocks.issueManualToken,
}));

afterEach(() => {
  cleanup();
  mocks.token = null;
  vi.clearAllMocks();
});

describe("admin supervision", () => {
  it("shows the refusal message when the administrator login fails", async () => {
    mocks.loginAdmin.mockRejectedValue(new Error("Identifiants administrateur invalides."));
    const user = userEvent.setup();
    render(<Admin />);

    await user.type(screen.getByLabelText("Identifiant"), "chef");
    await user.type(screen.getByLabelText("Mot de passe"), "faux");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));

    expect(await screen.findByText("Identifiants administrateur invalides.")).toBeInTheDocument();
    expect(mocks.getAdminOverview).not.toHaveBeenCalled();
  });

  it("logs in, loads the real overview and issues a reseller token", async () => {
    mocks.loginAdmin.mockResolvedValue({ access_token: "admin-token", admin: { username: "chef" } });
    mocks.getAdminOverview.mockResolvedValue(overview);
    mocks.issueManualToken.mockResolvedValue({ token: "VSE.abc.def", message: "" });
    const user = userEvent.setup();
    render(<Admin />);

    await user.type(screen.getByLabelText("Identifiant"), "chef");
    await user.type(screen.getByLabelText("Mot de passe"), "mot-de-passe-solide");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));

    expect(await screen.findByText("Supervision administrateur")).toBeInTheDocument();
    expect(mocks.loginAdmin).toHaveBeenCalledWith("chef", "mot-de-passe-solide");
    expect(mocks.getAdminOverview).toHaveBeenCalledWith("admin-token");
    expect(screen.getByText("Alertes ouvertes")).toBeInTheDocument();
    expect(screen.getByText("Goma · 12 compteurs")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Identifiant du compteur"), "VSF-000001");
    await user.click(screen.getByRole("button", { name: "Émettre" }));
    expect(await screen.findByText("VSE.abc.def")).toBeInTheDocument();
    expect(mocks.issueManualToken).toHaveBeenCalledWith("admin-token", "VSF-000001", 10);
  });
});
