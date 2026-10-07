import { useEffect, useState } from "react";
import { useAuth } from "@/_core/hooks/useAuth";
import { startLogin } from "@/const";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "wouter";
import { ArrowLeft, Cpu, Gauge, LockKeyhole, RadioTower } from "lucide-react";

type Overview = {
  totalMeters: number;
  onlineMeters: number;
  lowBalanceMeters: number;
  sectors: Array<{ name: string; online: number; offline: number }>;
};

export default function Admin() {
  const { user, isAuthenticated } = useAuth();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated || user?.role !== "admin") return;
    fetch("/api/admin/overview/")
      .then(response =>
        response.ok
          ? response.json()
          : Promise.reject(new Error("Accès refusé"))
      )
      .then(setOverview)
      .finally(() => setLoading(false));
  }, [isAuthenticated, user?.role]);

  if (!isAuthenticated || user?.role !== "admin")
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f7f4] p-6">
        <Card className="max-w-md border-0 shadow-xl">
          <CardContent className="p-8 text-center">
            <LockKeyhole className="mx-auto mb-4 h-10 w-10 text-emerald-700" />
            <h1 className="text-2xl font-semibold">Accès administrateur</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Cette vue est contrôlée par Django REST Framework côté serveur.
            </p>
            <Button className="mt-6 bg-[#0b3d36]" onClick={() => startLogin()}>
              Se connecter
            </Button>
            <Link href="/" className="mt-4 block text-sm text-emerald-700">
              Retour à l’espace abonné
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  if (loading || !overview)
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f7f4] text-sm text-slate-500">
        Chargement de la supervision…
      </div>
    );

  return (
    <div className="min-h-screen bg-[#f3f7f4]">
      <header className="bg-[#0b3d36] text-white">
        <div className="container flex items-center justify-between py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-100/70">
              Virunga Énergie
            </p>
            <h1 className="mt-1 text-xl font-semibold">
              Supervision administrateur
            </h1>
          </div>
          <Link
            href="/"
            className="flex items-center gap-2 text-sm text-emerald-100 hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" />
            Espace abonné
          </Link>
        </div>
      </header>
      <main className="container space-y-6 py-8">
        <div className="grid gap-4 sm:grid-cols-3">
          <Card className="border-0 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <Cpu className="h-8 w-8 text-emerald-700" />
              <div>
                <div className="text-2xl font-semibold">
                  {overview.totalMeters}
                </div>
                <div className="text-sm text-slate-500">Compteurs suivis</div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <RadioTower className="h-8 w-8 text-sky-700" />
              <div>
                <div className="text-2xl font-semibold">
                  {overview.onlineMeters}
                </div>
                <div className="text-sm text-slate-500">Compteurs en ligne</div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <Gauge className="h-8 w-8 text-amber-700" />
              <div>
                <div className="text-2xl font-semibold">
                  {overview.lowBalanceMeters}
                </div>
                <div className="text-sm text-slate-500">Soldes bas</div>
              </div>
            </CardContent>
          </Card>
        </div>
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>État par secteur</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
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
                    Supervision en lecture seule via Django REST Framework
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
        <p className="text-xs leading-5 text-slate-500">
          Les visuels territoriaux de la plateforme sont des illustrations
          éditoriales générées pour présenter le contexte ; ils ne constituent
          pas des preuves photographiques documentaires.
        </p>
      </main>
    </div>
  );
}
