import { useEffect, useRef, useState } from "react";

const SUBSCRIBER_TOKEN_KEY = "virunga-subscriber-token";

export type DjangoSnapshot = {
  mode: "DEMO" | "PERSISTED";
  meter: {
    id: string;
    location: string;
    sector: string;
    device_status: string;
    relay_status: boolean;
    signal_strength: number;
    firmware_version: string;
  };
  telemetry: {
    voltage: number;
    current: number;
    power: number;
    energy_consumed: number;
  };
  balance: { kwh: number; cdf: number; usd: number };
  cdf_per_usd?: number;
  estimate_hours: number;
  consumption: Array<{
    label: string;
    kwh: number;
    recharge?: "APP_PAIEMENT" | "SAISIE_MANUELLE";
  }>;
  consumption_daily: Array<{ label: string; kwh: number }> | null;
  consumption_weekly: Array<{
    label: string;
    date?: string;
    kwh: number;
  }> | null;
  alerts: Array<{
    kind: string;
    severity: string;
    message: string;
    created_at?: string;
  }> | null;
  last_telemetry_at: string | null;
  budget: { used_kwh: number; limit_kwh: number };
  recharges: Array<{
    id: string;
    source: "APP_PAIEMENT" | "SAISIE_MANUELLE";
    energy_kwh: number;
    status?: string;
    applied_at?: string | null;
    synced_at?: string;
  }>;
  relay_command?: {
    id: number;
    desired_state: "ON" | "OFF";
    status: "PENDING" | "APPLIED" | "SUPERSEDED";
  } | null;
};

export type SubscriberLogin = {
  firstName: string;
  lastName: string;
  meterCode: string;
  email?: string;
  phone?: string;
  address?: string;
};

export type SubscriberSession = {
  accessToken: string;
  subscriber: { firstName: string; lastName: string; meterId: string };
};

export type LocalNews = {
  id: number;
  title: string;
  summary: string;
  category: string;
  territory: string;
  image_url: string;
  source_url: string;
  published_at: string | null;
};

const DEMO_SNAPSHOT: DjangoSnapshot = {
  mode: "DEMO",
  meter: {
    id: "VSF-000001",
    location: "Quartier Himbi",
    sector: "Goma — Karisimbi",
    device_status: "ONLINE",
    relay_status: true,
    signal_strength: 86,
    firmware_version: "v2.4.1",
  },
  telemetry: {
    voltage: 220.4,
    current: 2.31,
    power: 508.2,
    energy_consumed: 0.084,
  },
  balance: { kwh: 18.42, cdf: 46050, usd: 18.42 },
  estimate_hours: 82.4,
  consumption: [
    { label: "06:00", kwh: 0.42 },
    { label: "09:00", kwh: 0.86 },
    { label: "12:00", kwh: 0.68 },
    { label: "15:00", kwh: 0.92, recharge: "APP_PAIEMENT" },
    { label: "18:00", kwh: 1.32 },
    { label: "21:00", kwh: 1.74, recharge: "SAISIE_MANUELLE" },
    { label: "00:00", kwh: 1.05 },
  ],
  consumption_daily: [
    { label: "Nuit", kwh: 1.05 },
    { label: "Matin", kwh: 1.94 },
    { label: "Après-midi", kwh: 2.6 },
    { label: "Soirée", kwh: 0.15 },
  ],
  consumption_weekly: [
    { label: "Lundi", kwh: 4.2, date: "2026-08-18" },
    { label: "Mardi", kwh: 3.8, date: "2026-08-19" },
    { label: "Mercredi", kwh: 4.5, date: "2026-08-20" },
    { label: "Jeudi", kwh: 3.2, date: "2026-08-21" },
    { label: "Vendredi", kwh: 4.9, date: "2026-08-22" },
    { label: "Samedi", kwh: 5.4, date: "2026-08-23" },
    { label: "Dimanche", kwh: 4.4, date: "2026-08-24" },
  ],
  alerts: [
    {
      kind: "SOLDE_BAS",
      severity: "WARNING",
      message: "Solde bas : 18.42 kWh restants.",
      created_at: "2026-08-24T10:20:00Z",
    },
  ],
  last_telemetry_at: "2026-08-24T10:24:26Z",
  budget: { used_kwh: 12.8, limit_kwh: 40 },
  recharges: [
    { id: "demo-app", source: "APP_PAIEMENT", energy_kwh: 10 },
    { id: "demo-manual", source: "SAISIE_MANUELLE", energy_kwh: 5 },
  ],
};

function authHeaders(accessToken?: string): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function parseJson<T>(response: Response): Promise<T> {
  const content = (await response.json().catch(() => ({}))) as T & {
    detail?: string;
  };
  if (!response.ok)
    throw new Error(content.detail || "Le serveur Django a refusé la requête.");
  return content;
}

export async function loginSubscriber(
  input: SubscriberLogin
): Promise<SubscriberSession> {
  const body: Record<string, unknown> = {
    first_name: input.firstName,
    last_name: input.lastName,
    meter_code: input.meterCode,
  };
  if (input.email) body.email = input.email;
  if (input.phone) body.phone = input.phone;
  if (input.address) body.address = input.address;
  const response = await fetch("/api/auth/subscriber/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  const data = await parseJson<{
    access_token: string;
    subscriber: { first_name: string; last_name: string; meter_id: string };
  }>(response);

  // MODIFICAION
  const token = data.access_token || "token-session-" + Date.now();
  // token au lieu de data.access_token
  const session = {
    accessToken: token,
    subscriber: {
      firstName: data.subscriber.first_name,
      lastName: data.subscriber.last_name,
      meterId: data.subscriber.meter_id,
    },
  };
  sessionStorage.setItem(SUBSCRIBER_TOKEN_KEY, session.accessToken);
  return session;
}

// Reconnexion automatique : le cookie persistant vse_refresh (HTTP-only) permet de
// récupérer un access token sans ressaisir ses identifiants.
export async function refreshSubscriberSession(): Promise<SubscriberSession> {
  const response = await fetch("/api/auth/token/refresh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({}),
  });
  const data = await parseJson<{
    access_token: string;
    subscriber: { first_name: string; last_name: string; meter_id: string };
  }>(response);
  const session = {
    accessToken: data.access_token,
    subscriber: {
      firstName: data.subscriber.first_name,
      lastName: data.subscriber.last_name,
      meterId: data.subscriber.meter_id,
    },
  };
  sessionStorage.setItem(SUBSCRIBER_TOKEN_KEY, session.accessToken);
  return session;
}

export async function logoutSubscriber(): Promise<void> {
  try {
    await fetch("/api/auth/subscriber/logout/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
  } catch {
    // Le cookie est effacé côté serveur ; on nettoie également localement.
  }
  sessionStorage.removeItem(SUBSCRIBER_TOKEN_KEY);
}

export function clearSubscriberSession() {
  sessionStorage.removeItem(SUBSCRIBER_TOKEN_KEY);
}

export function getSubscriberToken() {
  return sessionStorage.getItem(SUBSCRIBER_TOKEN_KEY);
}

export async function requestRelayCommand(
  accessToken: string,
  desiredState: "ON" | "OFF"
) {
  const response = await fetch("/api/relay/commands/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({ desired_state: desiredState }),
  });
  return parseJson<{
    id: number;
    status: "PENDING";
    desired_state: "ON" | "OFF";
    message: string;
  }>(response);
}

export function useDjangoDashboard(
  accessToken?: string | null,
  allowDemo = false
) {
  const [data, setData] = useState<DjangoSnapshot | null>(
    allowDemo ? DEMO_SNAPSHOT : null
  );
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setLoading] = useState(!allowDemo);
  const loadRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let active = true;
    if (!accessToken) {
      if (!allowDemo) {
        setError(new Error("Session abonné absente ou expirée."));
        setLoading(false);
      }
      return () => {
        active = false;
      };
    }
    const load = async () => {
      try {
        const response = await fetch("/api/dashboard/", {
          headers: authHeaders(accessToken),
        });
        const next = await parseJson<DjangoSnapshot>(response);
        if (!active) return;
        setData(next);
        setError(null);
      } catch (cause) {
        if (!active) return;
        setError(
          cause instanceof Error
            ? cause
            : new Error("Dashboard Django indisponible.")
        );
      } finally {
        if (active) setLoading(false);
      }
    };
    loadRef.current = load;
    load();
    const timer = window.setInterval(load, 5000);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${protocol}//${window.location.host}/ws/telemetry/`
    );
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data) as { type?: string };
        if (message.type === "telemetry.refresh") load();
      } catch {
        // Les messages non JSON ne modifient pas l’état du dashboard.
      }
    };
    return () => {
      active = false;
      window.clearInterval(timer);
      socket.close();
    };
  }, [accessToken, allowDemo]);

  const refresh = () => loadRef.current?.();
  return { data, error, isLoading, refresh };
}

export function useLocalNews() {
  const [data, setData] = useState<LocalNews[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/news/")
      .then(response =>
        parseJson<LocalNews[] | { results: LocalNews[] }>(response)
      )
      .then(response => {
        if (!active) return;
        setData(
          Array.isArray(response)
            ? response
            : Array.isArray(response.results)
              ? response.results
              : []
        );
        setError(null);
      })
      .catch(
        cause =>
          active &&
          setError(
            cause instanceof Error
              ? cause
              : new Error("Actualités indisponibles.")
          )
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  return { data, error, isLoading };
}

export async function askDjangoAssistant(
  question: string,
  accessToken?: string | null
) {
  const response = await fetch("/api/assistant/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken ?? undefined),
    },
    body: JSON.stringify({ question }),
  });
  return parseJson<{ answer: string }>(response);
}

export async function initiatePayment(
  accessToken: string,
  provider: "pawapay" | "flutterwave",
  amountCdf: number,
  opts?: { phoneNumber?: string; network?: string }
) {
  const body: Record<string, unknown> = { provider, amount_cdf: amountCdf };
  if (opts?.phoneNumber) body.phone_number = opts.phoneNumber;
  if (opts?.network) body.network = opts.network;
  const response = await fetch("/api/payments/initiate/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken),
    },
    body: JSON.stringify(body),
  });
  return parseJson<{
    provider: string;
    deposit_id?: string;
    tx_ref?: string;
    http_status?: number;
    status?: string;
    accepted?: boolean;
    link?: string;
    detail: string;
  }>(response);
}

export async function getPawaPayStatus(accessToken: string, depositId: string) {
  const response = await fetch(
    `/api/payments/pawapay/status/${encodeURIComponent(depositId)}/`,
    { headers: authHeaders(accessToken) }
  );
  return parseJson<{
    deposit_id: string;
    http_status?: number;
    status: string;
    customer_message?: string;
    provider_transaction_id?: string;
    applied?: boolean;
    recharge_id?: string;
    balance_kwh?: number;
    failed?: boolean;
    detail?: string;
  }>(response);
}

export async function applyManualToken(accessToken: string, token: string) {
  const response = await fetch("/api/recharges/manual/apply/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({ token }),
  });
  return parseJson<{
    applied: boolean;
    recharge_id: string;
    source: string;
    energy_kwh: number;
    balance_kwh: number;
    applied_at?: string;
    relay_status: string;
  }>(response);
}

export async function getBudget(accessToken: string) {
  const response = await fetch("/api/budget/", {
    headers: authHeaders(accessToken),
  });
  return parseJson<{
    limit_kwh: number;
    warning_percentage: number;
    balance_kwh: number;
  }>(response);
}

export async function updateBudget(accessToken: string, limitKwh: number) {
  const response = await fetch("/api/budget/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({ limit_kwh: limitKwh }),
  });
  return parseJson<{
    limit_kwh: number;
    warning_percentage: number;
    balance_kwh: number;
  }>(response);
}

export async function downloadReceiptPdf(
  accessToken: string,
  rechargeId: string
) {
  const response = await fetch(
    `/api/receipts/${encodeURIComponent(rechargeId)}/`,
    { headers: authHeaders(accessToken) }
  );
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Téléchargement du reçu impossible."
    );
  return await response.blob();
}
