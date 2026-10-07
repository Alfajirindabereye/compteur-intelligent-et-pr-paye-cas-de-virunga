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
  tariff?: { cdf_per_kwh: number; usd_per_kwh: number };
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
  credit?: {
    percent: number | null;
    reference_kwh: number;
    threshold: number | null;
    thresholds: number[];
  };
  notifications?: Record<NotificationChannel, ChannelState>;
  alerts: Array<{
    id?: number;
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

export type NotificationChannel = "email" | "sms" | "whatsapp";
export type ChannelState = "ready" | "no_contact" | "not_configured";

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

type AuthResponse = {
  access_token?: string;
  subscriber?: { first_name?: string; last_name?: string; meter_id?: string };
};

// Lecture défensive de la réponse d'authentification : un corps inattendu (proxy,
// ancienne version du serveur…) produit un message clair plutôt qu'un
// « Cannot read properties of undefined (reading 'first_name') ».
function toSession(
  data: AuthResponse | null | undefined,
  fallback?: { firstName: string; lastName: string }
): SubscriberSession {
  if (!data?.access_token)
    throw new Error("Réponse de connexion incomplète : jeton d'accès absent.");
  const session: SubscriberSession = {
    accessToken: data.access_token,
    subscriber: {
      firstName: data.subscriber?.first_name ?? fallback?.firstName ?? "",
      lastName: data.subscriber?.last_name ?? fallback?.lastName ?? "",
      meterId: data.subscriber?.meter_id ?? "",
    },
  };
  sessionStorage.setItem(SUBSCRIBER_TOKEN_KEY, session.accessToken);
  return session;
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
  return toSession(await parseJson<AuthResponse>(response), input);
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
  return toSession(await parseJson<AuthResponse>(response));
}

let pendingRefresh: Promise<SubscriberSession> | null = null;

// Toute requête abonné passe ici : le jeton le plus récent est envoyé en
// « Authorization: Bearer … » et, s'il a expiré (401), la session est renouvelée
// une fois par le cookie de rafraîchissement avant de rejouer la requête.
async function authorizedFetch(
  accessToken: string | null | undefined,
  url: string,
  init: RequestInit = {}
): Promise<Response> {
  const send = (token: string | null | undefined) =>
    fetch(url, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...authHeaders(token ?? undefined),
      },
    });
  const response = await send(getSubscriberToken() ?? accessToken);
  if (response.status !== 401) return response;
  try {
    pendingRefresh ??= refreshSubscriberSession().finally(() => {
      pendingRefresh = null;
    });
    const session = await pendingRefresh;
    return await send(session.accessToken);
  } catch {
    return response;
  }
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
  const response = await authorizedFetch(accessToken, "/api/relay/commands/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
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
        const response = await authorizedFetch(
          accessToken,
          "/api/dashboard/",
          {}
        );
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
  const response = await authorizedFetch(accessToken, "/api/assistant/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
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
  const response = await authorizedFetch(
    accessToken,
    "/api/payments/initiate/",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );
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
  const response = await authorizedFetch(
    accessToken,
    `/api/payments/pawapay/status/${encodeURIComponent(depositId)}/`,
    {}
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
  const response = await authorizedFetch(
    accessToken,
    "/api/recharges/manual/apply/",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token }),
    }
  );
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
  const response = await authorizedFetch(accessToken, "/api/budget/", {});
  return parseJson<{
    limit_kwh: number;
    warning_percentage: number;
    balance_kwh: number;
  }>(response);
}

export async function updateBudget(accessToken: string, limitKwh: number) {
  const response = await authorizedFetch(accessToken, "/api/budget/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
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
  const response = await authorizedFetch(
    accessToken,
    `/api/receipts/${encodeURIComponent(rechargeId)}/`,
    {}
  );
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Téléchargement du reçu impossible."
    );
  return await response.blob();
}

export type SubscriberProfile = {
  first_name: string;
  last_name: string;
  meter_id: string;
  email: string;
  phone: string;
  address: string;
  channels: Record<NotificationChannel, ChannelState>;
};

export async function getProfile(accessToken: string) {
  const response = await authorizedFetch(accessToken, "/api/profile/");
  return parseJson<SubscriberProfile>(response);
}

export async function updateProfile(
  accessToken: string,
  contact: { email?: string; phone?: string; address?: string }
) {
  const response = await authorizedFetch(accessToken, "/api/profile/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(contact),
  });
  const content = (await response
    .json()
    .catch(() => ({}))) as SubscriberProfile & {
    detail?: string;
    email?: string | string[];
    phone?: string | string[];
  };
  if (!response.ok) {
    // Erreurs de validation DRF : { champ: ["message"] }
    const fieldError = [content.phone, content.email].find(Array.isArray) as
      | string[]
      | undefined;
    throw new Error(
      fieldError?.[0] ||
        content.detail ||
        "Coordonnées refusées par le serveur."
    );
  }
  return content as SubscriberProfile;
}

export async function sendTestNotification(accessToken: string) {
  const response = await authorizedFetch(
    accessToken,
    "/api/notifications/test/",
    { method: "POST", headers: { "Content-Type": "application/json" } }
  );
  return parseJson<{ results: Record<NotificationChannel, string> }>(response);
}

export async function acknowledgeAlert(accessToken: string, alertId: number) {
  const response = await authorizedFetch(
    accessToken,
    `/api/alerts/${alertId}/ack/`,
    { method: "POST", headers: { "Content-Type": "application/json" } }
  );
  return parseJson<{ acknowledged: boolean; open_alerts: number }>(response);
}

// --- Espace administrateur (compte Django is_staff) ---

const ADMIN_TOKEN_KEY = "virunga-admin-token";

export type AdminOverview = {
  totalMeters: number;
  onlineMeters: number;
  lowBalanceMeters: number;
  openAlerts: number;
  sectors: Array<{
    name: string;
    territory: string;
    online: number;
    offline: number;
    total: number;
  }>;
};

export function getAdminToken() {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY);
}

export function clearAdminSession() {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

export async function loginAdmin(username: string, password: string) {
  const response = await fetch("/api/auth/admin/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await parseJson<{
    access_token: string;
    admin: { username: string };
  }>(response);
  sessionStorage.setItem(ADMIN_TOKEN_KEY, data.access_token);
  return data;
}

export async function getAdminOverview(accessToken: string) {
  const response = await fetch("/api/admin/overview/", {
    headers: authHeaders(accessToken),
  });
  return parseJson<AdminOverview>(response);
}

export async function issueManualToken(
  accessToken: string,
  meterId: string,
  energyKwh: number
) {
  const response = await fetch("/api/recharges/manual/issue/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({ meter_id: meterId, energy_kwh: energyKwh }),
  });
  return parseJson<{ token: string; message: string }>(response);
}
