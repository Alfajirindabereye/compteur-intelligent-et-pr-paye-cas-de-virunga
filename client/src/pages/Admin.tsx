import React, { useEffect, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  clearAdminSession,
  getAdminOverview,
  getAdminToken,
  issueManualToken,
  loginAdmin,
  type AdminOverview,
} from "@/lib/djangoEnergy";
import { Link } from "wouter";
import {
  ArrowLeft,
  BellRing,
  Cpu,
  Gauge,
  LockKeyhole,
  LogOut,
  RadioTower,
} from "lucide-react";

function AdminLogin({ onLogin }: { onLogin: (token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await loginAdmin(username.trim(), password);
      onLogin(session.access_token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f3f7f4] p-6">
      <Card className="w-full max-w-md border-0 shadow-xl">
        <CardContent className="p-8">
          <LockKeyhole className="mx-auto mb-4 h-10 w-10 text-emerald-700" />
          <h1 className="text-center text-2xl font-semibold">
            Accès administrateur
          </h1>
          <p className="mt-2 text-center text-sm leading-6 text-slate-500">
            Réservé aux comptes administrateurs de la plateforme.
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <Label htmlFor="admin-username">Identifiant</Label>
              <Input
                id="admin-username"
                className="mt-2 h-11"
                autoComplete="username"
                value={username}
                onChange={event => setUsername(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="admin-password">Mot de passe</Label>
              <Input
                id="admin-password"
                type="password"
                className="mt-2 h-11"
                autoComplete="current-password"
                value={password}
                onChange={event => setPassword(event.target.value)}
                required
              />
            </div>
            {error && (
              <p className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={busy}
              className="h-11 w-full bg-[#0b3d36]"
            >
              {busy ? "Connexion…" : "Se connecter"}
            </Button>
          </form>
          <Link
            href="/"
            className="mt-4 block text-center text-sm text-emerald-700"
          >
            Retour à l’espace abonné
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function TokenIssuer({ token }: { token: string }) {
  const [meterId, setMeterId] = useState("");
  const [energy, setEnergy] = useState("10");
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = Number(energy);
    if (!meterId.trim() || !Number.isFinite(parsed) || parsed <= 0) {
      setError("Indiquez un compteur et une énergie positive.");
      return;
    }
    setBusy(true);
    setError("");
    setIssued("");
    try {
      const result = await issueManualToken(token, meterId.trim(), parsed);
      setIssued(result.token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Émission impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader>
        <CardTitle>Émettre un token de recharge (revendeur)</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={submit}
          className="grid gap-3 sm:grid-cols-[1fr_140px_auto] sm:items-end"
        >
          <div>
            <Label htmlFor="issue-meter">Identifiant du compteur</Label>
            <Input
              id="issue-meter"
              className="mt-2 h-10 font-mono"
              placeholder="VSF-DEMO-ALF-001"
              value={meterId}
              onChange={event => setMeterId(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="issue-energy">Énergie (kWh)</Label>
            <Input
              id="issue-energy"
              type="number"
              min="0.001"
              step="any"
              className="mt-2 h-10"
              value={energy}
              onChange={event => setEnergy(event.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy} className="h-10 bg-[#0b3d36]">
            {busy ? "Émission…" : "Émettre"}
          </Button>
        </form>
        {error && <p className="mt-3 text-xs text-red-600">{error}</p>}
        {issued && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
            <p className="text-xs font-semibold text-emerald-800">
              Token à transmettre à l’abonné (utilisable une seule fois) :
            </p>
            <p className="mt-2 break-all font-mono text-xs text-slate-700">
              {issued}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Admin() {
  const [token, setToken] = useState<string | null>(() => getAdminToken());
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState("");

  const logout = () => {
    clearAdminSession();
    setToken(null);
    setOverview(null);
  };

  useEffect(() => {
    if (!token) return;
    let active = true;
    const load = () =>
      getAdminOverview(token)
        .then(next => {
          if (!active) return;
          setOverview(next);
          setError("");
        })
        .catch(cause => {
          if (!active) return;
          setError(
            cause instanceof Error ? cause.message : "Supervision indisponible."
          );
        });
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [token]);

  if (!token) return <AdminLogin onLogin={setToken} />;
  if (!overview)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f3f7f4] p-6 text-center text-sm text-slate-500">
        {error ? (
          <>
            <p>{error}</p>
            <Button variant="outline" onClick={logout}>
              Se reconnecter
            </Button>
          </>
        ) : (
          "Chargement de la supervision…"
        )}
      </div>
    );

  const stats = [
    {
      label: "Compteurs suivis",
      value: overview.totalMeters,
      icon: Cpu,
      tone: "text-emerald-700",
    },
    {
      label: "Compteurs en ligne",
      value: overview.onlineMeters,
      icon: RadioTower,
      tone: "text-sky-700",
    },
    {
      label: "Soldes bas",
      value: overview.lowBalanceMeters,
      icon: Gauge,
      tone: "text-amber-700",
    },
    {
      label: "Alertes ouvertes",
      value: overview.openAlerts,
      icon: BellRing,
      tone: "text-red-600",
    },
  ];

  return (
    <div className="min-h-screen bg-[#f3f7f4]">
      <header className="bg-[#0b3d36] text-white">
        <div className="container flex items-center justify-between gap-4 py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-100/70">
              Virunga Énergie
            </p>
            <h1 className="mt-1 text-xl font-semibold">
              Supervision administrateur
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-2 text-sm text-emerald-100 hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" />
              Espace abonné
            </Link>
            <button
              onClick={logout}
              className="flex items-center gap-2 text-sm text-emerald-100 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              Se déconnecter
            </button>
          </div>
        </div>
      </header>
      <main className="container space-y-6 py-8">
        {error && (
          <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            Dernière actualisation impossible : {error}
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map(stat => {
            const Icon = stat.icon;
            return (
              <Card key={stat.label} className="border-0 shadow-sm">
                <CardContent className="flex items-center gap-4 p-5">
                  <Icon className={`h-8 w-8 ${stat.tone}`} />
                  <div>
                    <div className="text-2xl font-semibold">{stat.value}</div>
                    <div className="text-sm text-slate-500">{stat.label}</div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>État par secteur</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {overview.sectors.length === 0 && (
              <p className="text-sm text-slate-500">
                Aucun secteur enregistré.
              </p>
            )}
            {overview.sectors.map(sector => (
              <div
                key={sector.name}
                className="flex flex-col justify-between gap-3 rounded-xl border border-slate-100 p-4 sm:flex-row sm:items-center"
              >
                <div>
                  <div className="font-semibold text-slate-800">
                    {sector.name}
                  </div>
                  <div className="mt-1 text-sm text-slate-500">
                    {sector.territory} · {sector.total} compteur
                    {sector.total > 1 ? "s" : ""}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Badge className="border-0 bg-emerald-100 text-emerald-700">
                    {sector.online} en ligne
                  </Badge>
                  <Badge className="border-0 bg-slate-100 text-slate-600">
                    {sector.offline} hors ligne
                  </Badge>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
        <TokenIssuer token={token} />
        <p className="text-xs leading-5 text-slate-500">
          Les visuels territoriaux de la plateforme sont des illustrations
          éditoriales générées pour présenter le contexte ; ils ne constituent
          pas des preuves photographiques documentaires.
        </p>
      </main>
    </div>
  );
}
