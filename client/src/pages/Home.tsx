import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  applyManualToken,
  askDjangoAssistant,
  clearSubscriberSession,
  downloadReceiptPdf,
  getBudget,
  getPawaPayStatus,
  initiatePayment,
  loginSubscriber,
  requestRelayCommand,
  updateBudget,
  useDjangoDashboard,
  useLocalNews,
  type DjangoSnapshot,
} from "@/lib/djangoEnergy";
import { isValidMeterCode, normalizeMeterCode } from "@/lib/meterValidation";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BellRing,
  Bolt,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleDollarSign,
  CircleGauge,
  Clock3,
  Code2,
  Cpu,
  Database,
  FileText,
  Gauge as GaugeIcon,
  History,
  Info,
  LayoutDashboard,
  Leaf,
  LockKeyhole,
  LogOut,
  Menu,
  Paintbrush,
  Power,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Signal,
  Timer,
  TrendingUp,
  Wifi,
  Wallet,
  X,
  Zap,
  Bot,
  CreditCard,
  Download,
  Loader2,
  Send,
  Smartphone,
  Moon,
  Sun,
} from "lucide-react";
import { Streamdown } from "streamdown";
const assets = {
  logo: "/img/logo.png",
  territory: "/img/hydro-matebe-aerien.jpg",
  conservation: "/manus-storage/virunga-conservation-gorilla-monkey.svg",
  smartMeter: "/img/techniciens-poteau.jpg",
  solution: "/img/centralien-pylone.jpg",
  technicians: "/img/electrification-rurale.jpg",
};
const format = (value: number, digits = 2) =>
  new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits }).format(
    value
  );
type Subscriber = {
  firstName: string;
  lastName: string;
  meterCode: string;
  accessToken?: string;
};
function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    return (
      (localStorage.getItem("virunga-theme") as "light" | "dark") || "light"
    );
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("virunga-theme", theme);
  }, [theme]);
  const toggle = () => setTheme(prev => (prev === "dark" ? "light" : "dark"));
  return { theme, toggle };
}
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      aria-label="Basculer le thème"
      title={theme === "dark" ? "Mode clair" : "Mode sombre"}
      onClick={toggle}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </button>
  );
}
function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <img
        src={assets.logo}
        alt="Virunga Energies"
        className="h-10 w-10 shrink-0 rounded-full object-contain"
      />
      <div className="min-w-0">
        <p
          className={`truncate text-sm font-black tracking-[.16em] ${dark ? "text-zinc-100" : "text-zinc-950"}`}
        >
          VIRUNGA ENERGIES
        </p>
        <p className="text-[10px] tracking-[.14em] text-zinc-500">
          NORD-KIVU · ÉNERGIE UTILE
        </p>
      </div>
    </div>
  );
}
function PublicView({ login }: { login: () => void }) {
  const [index, setIndex] = useState(0);
  const [menu, setMenu] = useState(false);
  const {
    data: news,
    error: newsError,
    isLoading: newsLoading,
  } = useLocalNews();
  const slides = [
    [
      assets.territory,
      "MATEBE · RUTSHURU",
      "Une infrastructure pensée pour le Nord-Kivu.",
      "Des réseaux de distribution au plus près des ménages, des activités et des services essentiels.",
    ],
    [
      assets.smartMeter,
      "GOMA · PRÉPAYÉ",
      "Recharger simplement. Suivre précisément.",
      "Le compteur intelligent rend le crédit et la consommation plus faciles à comprendre.",
    ],
    [
      assets.technicians,
      "RÉSEAU · TERRAIN",
      "Des techniciens au plus près du réseau.",
      "Installation, contrôle et maintenance des lignes de distribution au service des communautés.",
    ],
    [
      assets.solution,
      "RÉSEAU · TERRITOIRE",
      "Voir l'énergie, agir avec confiance.",
      "Une information utile pour les équipes terrain comme pour les abonnés.",
    ],
  ];
  const current = slides[index];
  const move = (direction: number) =>
    setIndex(value => (value + direction + slides.length) % slides.length);
  const promos = [
    [
      "/img/centrale-matebe.jpg",
      "Production",
      "La force de l'hydroélectricité",
      "Dans la salle des machines de la centrale de Matebe, les turbines transforment l'eau du territoire en énergie propre et locale.",
    ],
    [
      "/img/hydro-matebe-aerien.jpg",
      "Production",
      "Matebe, l'énergie qui coule de source",
      "Le canal d'amenée de la centrale de Matebe vu du ciel : une infrastructure pensée pour le Nord-Kivu.",
    ],
    [
      "/img/electrification-rurale.jpg",
      "Électrification",
      "Au plus près des villages",
      "Poteaux, câbles et communautés : l'électrification avance au cœur des villages du Nord-Kivu.",
    ],
    [
      "/img/techniciens-poteau.jpg",
      "Réseau",
      "Un réseau entretenu et fiable",
      "Femmes et hommes du terrain, les techniciens installent et entretiennent les coffrets électriques.",
    ],
    [
      "/img/pylones-champs.jpg",
      "Réseau",
      "L'énergie qui circule",
      "Les équipes hissent les lignes au-dessus des champs pour relier les centrales aux foyers.",
    ],
    [
      "/img/centralien-pylone.jpg",
      "Équipe",
      "En hauteur, au service du courant",
      "Les monteurs du réseau travaillent en altitude pour une électricité toujours disponible.",
    ],
    [
      "/img/gorille-brousse.jpg",
      "Conservation",
      "Protéger les gorilles",
      "Le Parc des Virunga abrite l'une des dernières populations de gorilles de montagne au monde.",
    ],
    [
      "/img/gorille-trekking.jpg",
      "Conservation",
      "Un sanctuaire de biodiversité",
      "Le trekking dans les Virunga fait découvrir les grands singes et soutient leur protection.",
    ],
    [
      "/img/singe-dore.png",
      "Biodiversité",
      "Le singe doré des Virunga",
      "Espèce emblématique endémique, le singe doré vit dans les forêts du parc.",
    ],
    [
      "/img/grue-couronnee.png",
      "Biodiversité",
      "La grue couronnée",
      "Majestueux oiseau des zones humides, il rappelle l'équilibre entre énergie et nature.",
    ],
    [
      "/img/matebe-barrage.jpg",
      "Production",
      "Le barrage de Matebe",
      "Le canal de dérivation de la centrale de Matebe : une énergie hydraulique au service du territoire.",
    ],
    [
      "/img/virunga-volcan.jpg",
      "Territoire",
      "Le Virunga dans toute sa beauté",
      "Volcans et forêts primaires : un paysage unique, entre énergie et préservation.",
    ],
  ];
  return (
    <div className="min-h-screen overflow-x-clip bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b border-zinc-200 bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-3 px-4 sm:px-5 lg:px-8">
          <Brand />
          <nav className="hidden gap-8 text-sm font-semibold text-zinc-600 md:flex">
            <a href="#accueil">Accueil</a>
            <a href="#impact">Impact Social</a>
            <a href="#actualites">Actualités</a>
          </nav>
          <ThemeToggle />
          <Button
            onClick={login}
            className="hidden shrink-0 rounded-md bg-emerald-800 px-5 hover:bg-emerald-950 md:inline-flex"
          >
            Espace Abonné <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="shrink-0 md:hidden"
            aria-label="Ouvrir le menu"
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X /> : <Menu />}
          </Button>
        </div>
        {menu && (
          <div className="border-t border-zinc-200 bg-white px-5 py-5 md:hidden">
            <div className="flex flex-col gap-4 text-sm font-semibold">
              <a onClick={() => setMenu(false)} href="#accueil">
                Accueil
              </a>
              <a onClick={() => setMenu(false)} href="#impact">
                Impact Social
              </a>
              <a onClick={() => setMenu(false)} href="#actualites">
                Actualités
              </a>
              <Button
                onClick={() => {
                  setMenu(false);
                  login();
                }}
                className="bg-emerald-800"
              >
                Espace Abonné
              </Button>
            </div>
          </div>
        )}
      </header>
      <main id="accueil">
        <section className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-5 lg:grid-cols-[.9fr_1.1fr] lg:px-8 lg:py-20">
          <div className="flex flex-col justify-center">
            <p className="text-xs font-bold uppercase tracking-[.18em] text-emerald-800">
              ● Énergie locale, impact durable
            </p>
            <h1 className="mt-6 max-w-xl text-5xl font-black leading-[.96] tracking-[-.055em] sm:text-6xl lg:text-7xl">
              L’énergie qui éclaire le quotidien.
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-zinc-600">
              Virunga Energies accompagne les communautés de Goma, Rutshuru et
              Matebe avec une énergie fiable, des compteurs intelligents et une
              vision territoriale durable.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button
                onClick={login}
                className="rounded-md bg-emerald-800 px-6 hover:bg-emerald-950"
              >
                Accéder à mon compteur
              </Button>
              <Button
                variant="outline"
                className="rounded-md border-zinc-300 bg-transparent px-6"
                onClick={() =>
                  document
                    .getElementById("impact")
                    ?.scrollIntoView({ behavior: "smooth" })
                }
              >
                Découvrir notre impact
              </Button>
            </div>
            <div className="mt-10 grid grid-cols-3 gap-3 border-t border-zinc-200 pt-6">
              <div>
                <b className="text-xl">24/7</b>
                <p className="mt-1 text-xs text-zinc-500">Suivi compteur</p>
              </div>
              <div>
                <b className="text-xl">HTTPS</b>
                <p className="mt-1 text-xs text-zinc-500">Flux signé</p>
              </div>
              <div>
                <b className="text-xl">Local</b>
                <p className="mt-1 text-xs text-zinc-500">Nord-Kivu</p>
              </div>
            </div>
          </div>
          <div className="relative min-h-[360px] overflow-hidden rounded-2xl bg-zinc-900 shadow-2xl sm:min-h-[470px]">
            <img
              src={current[0]}
              alt={current[2]}
              className="absolute inset-0 h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/15 to-transparent" />
            <span className="absolute left-5 top-5 border border-white/30 bg-black/20 px-3 py-1 text-[10px] font-bold tracking-[.14em] text-white backdrop-blur sm:left-6 sm:top-6">
              {current[1]}
            </span>
            <div className="absolute bottom-0 p-6 text-white sm:p-8">
              <h2 className="max-w-lg text-2xl font-black tracking-[-.03em] sm:text-3xl">
                {current[2]}
              </h2>
              <p className="mt-3 max-w-lg text-sm leading-6 text-white/75">
                {current[3]}
              </p>
            </div>
            <div className="absolute right-4 top-1/2 flex -translate-y-1/2 flex-col gap-2 sm:right-5">
              <Button
                aria-label="Précédent"
                size="icon"
                variant="outline"
                className="border-white/30 bg-black/20 text-white"
                onClick={() => move(-1)}
              >
                <ChevronLeft />
              </Button>
              <Button
                aria-label="Suivant"
                size="icon"
                variant="outline"
                className="border-white/30 bg-black/20 text-white"
                onClick={() => move(1)}
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
        </section>
        <section id="impact" className="border-y border-zinc-200 bg-white">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-5 lg:px-8 lg:py-20">
            <p className="text-xs font-bold uppercase tracking-[.18em] text-emerald-800">
              Impact Social
            </p>
            <div className="mt-4 flex flex-col justify-between gap-5 md:flex-row">
              <h2 className="max-w-xl text-4xl font-black tracking-[-.04em]">
                Une énergie conçue avec le territoire.
              </h2>
              <p className="max-w-md text-sm leading-6 text-zinc-600">
                Qualité de service, proximité terrain, conservation et outils
                numériques simples à utiliser.
              </p>
            </div>
            <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-zinc-200 bg-zinc-200 md:grid-cols-3">
              <article className="bg-white p-7">
                <Zap className="h-5 w-5 text-emerald-800" />
                <h3 className="mt-7 text-xl font-bold">Énergie durable</h3>
                <p className="mt-3 text-sm leading-6 text-zinc-600">
                  Des infrastructures et un suivi qui rendent l’accès à
                  l’énergie plus lisible.
                </p>
              </article>
              <article className="bg-white p-7">
                <Leaf className="h-5 w-5 text-lime-700" />
                <h3 className="mt-7 text-xl font-bold">Conservation active</h3>
                <p className="mt-3 text-sm leading-6 text-zinc-600">
                  Une vision qui reconnaît les paysages et le vivant du Virunga.
                </p>
              </article>
              <article className="bg-white p-7">
                <Cpu className="h-5 w-5 text-sky-700" />
                <h3 className="mt-7 text-xl font-bold">Comptage intelligent</h3>
                <p className="mt-3 text-sm leading-6 text-zinc-600">
                  Crédit, consommation et état du compteur dans un espace
                  sécurisé.
                </p>
              </article>
            </div>
          </div>
        </section>
        <section
          id="engagements"
          className="mx-auto max-w-7xl px-4 py-16 sm:px-5 lg:px-8 lg:py-20"
        >
          <p className="text-xs font-bold uppercase tracking-[.18em] text-emerald-800">
            En images
          </p>
          <h2 className="mt-4 text-4xl font-black tracking-[-.04em]">
            Le Virunga de l'énergie, comme si vous y étiez.
          </h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {promos.map(([image, badge, title, text]) => (
              <article
                key={image}
                className="group flex min-h-full flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white"
              >
                <div className="h-52 overflow-hidden bg-zinc-100">
                  <img
                    src={image}
                    alt={title}
                    className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                </div>
                <div className="flex flex-1 flex-col p-6">
                  <p className="text-[10px] font-bold uppercase tracking-[.14em] text-emerald-800">
                    {badge}
                  </p>
                  <h3 className="mt-3 text-xl font-bold">{title}</h3>
                  <p className="mt-3 flex-1 text-sm leading-6 text-zinc-600">
                    {text}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section
          id="actualites"
          className="mx-auto max-w-7xl px-4 py-16 sm:px-5 lg:px-8 lg:py-20"
        >
          <p className="text-xs font-bold uppercase tracking-[.18em] text-emerald-800">
            Actualités
          </p>
          <h2 className="mt-4 text-4xl font-black tracking-[-.04em]">
            Sur le terrain, au plus près des usages.
          </h2>
          {newsLoading && (
            <div className="mt-10 border border-zinc-200 bg-white p-6 text-sm text-zinc-500">
              Chargement des actualités publiées…
            </div>
          )}
          {newsError && (
            <div className="mt-10 border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
              Les actualités sont momentanément indisponibles.
            </div>
          )}
          {!newsLoading && !newsError && news.length === 0 && (
            <div className="mt-10 border border-zinc-200 bg-white p-6 text-sm leading-6 text-zinc-600">
              Aucune actualité locale n’est publiée pour le moment. Les
              informations de projet, extension du réseau et maintenance
              apparaîtront ici dès leur publication par l’équipe habilitée.
            </div>
          )}
          {news.length > 0 && (
            <div className="mt-10 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {news.map(article => (
                <article
                  key={article.id}
                  className="flex min-h-full flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white"
                >
                  <div className="h-48 bg-zinc-100">
                    {article.image_url ? (
                      <img
                        src={article.image_url}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center bg-gradient-to-br from-emerald-900 to-zinc-900 p-6 text-center text-xs font-bold tracking-[.14em] text-lime-200">
                        VIRUNGA ENERGIES
                        <br />
                        {article.territory}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-1 flex-col p-6">
                    <div className="flex flex-wrap gap-2 text-[10px] font-bold tracking-[.14em] text-emerald-800">
                      <span>{article.category}</span>
                      <span className="text-zinc-400">/</span>
                      <span>{article.territory}</span>
                    </div>
                    <h3 className="mt-3 text-xl font-bold">{article.title}</h3>
                    <p className="mt-3 flex-1 text-sm leading-6 text-zinc-600">
                      {article.summary}
                    </p>
                    {article.source_url && (
                      <a
                        className="mt-5 text-sm font-semibold text-emerald-800 underline underline-offset-4"
                        href={article.source_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Lire la source
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
      <footer className="bg-zinc-950 px-4 py-10 text-zinc-400 sm:px-5">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-5 md:flex-row lg:px-3">
          <Brand dark />
          <p className="max-w-sm text-xs leading-5">
            Les visuels locaux sont des illustrations éditoriales et ne
            constituent pas des preuves photographiques documentaires.
          </p>
        </div>
      </footer>
    </div>
  );
}

function Login({
  open,
  setOpen,
  submit,
}: {
  open: boolean;
  setOpen: (value: boolean) => void;
  submit: (value: Subscriber) => Promise<void>;
}) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [meterCode, setMeterCode] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const valid =
    firstName.trim().length > 1 &&
    lastName.trim().length > 1 &&
    isValidMeterCode(meterCode);
  const send = async () => {
    setAttempted(true);
    setServerError("");
    if (!valid) return;
    setSubmitting(true);
    try {
      await submit({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        meterCode,
      });
      setOpen(false);
    } catch (error) {
      setServerError(
        error instanceof Error ? error.message : "Connexion impossible."
      );
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md rounded-xl border-zinc-200 p-0">
        <div className="bg-zinc-950 px-6 py-6 sm:px-7">
          <Brand dark />
        </div>
        <div className="p-6 sm:p-7">
          <DialogHeader>
            <DialogTitle className="text-2xl font-black">
              Espace Abonné
            </DialogTitle>
            <DialogDescription>
              Saisissez votre identité et le code à 20 chiffres associé à votre
              compteur intelligent.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-7 space-y-5">
            <div>
              <Label htmlFor="nom">Nom</Label>
              <Input
                id="nom"
                className="mt-2 h-11"
                value={lastName}
                onChange={event => setLastName(event.target.value)}
                placeholder="Ex. Kambale"
              />
              {attempted && lastName.trim().length < 2 && (
                <p className="mt-1 text-xs text-red-600">Le nom est requis.</p>
              )}
            </div>
            <div>
              <Label htmlFor="prenom">Prénom</Label>
              <Input
                id="prenom"
                className="mt-2 h-11"
                value={firstName}
                onChange={event => setFirstName(event.target.value)}
                placeholder="Ex. Amani"
              />
              {attempted && firstName.trim().length < 2 && (
                <p className="mt-1 text-xs text-red-600">
                  Le prénom est requis.
                </p>
              )}
            </div>
            <div>
              <Label htmlFor="compteur">Code du compteur</Label>
              <Input
                id="compteur"
                className={`mt-2 h-11 font-mono tracking-[.08em] ${attempted && !isValidMeterCode(meterCode) ? "border-red-500" : ""}`}
                inputMode="numeric"
                maxLength={20}
                value={meterCode}
                onChange={event =>
                  setMeterCode(normalizeMeterCode(event.target.value))
                }
                placeholder="20 chiffres"
              />
              <div className="mt-2 flex justify-between text-xs">
                <span
                  className={
                    isValidMeterCode(meterCode)
                      ? "text-emerald-700"
                      : "text-zinc-500"
                  }
                >
                  {meterCode.length}/20 chiffres
                </span>
                {attempted && !isValidMeterCode(meterCode) && (
                  <span className="text-red-600">Code invalide.</span>
                )}
              </div>
            </div>
            {serverError && (
              <p
                role="alert"
                className="rounded-md border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-700"
              >
                {serverError}
              </p>
            )}
          </div>
          <DialogFooter className="mt-8">
            <Button
              disabled={submitting}
              onClick={send}
              className="h-11 w-full bg-emerald-800 hover:bg-emerald-950"
            >
              <LockKeyhole className="mr-2 h-4 w-4" />
              {submitting
                ? "Vérification sécurisée…"
                : "Accéder à mon espace sécurisé"}
            </Button>
          </DialogFooter>
          <p className="mt-4 text-center text-[11px] text-zinc-500">
            <ShieldCheck className="mr-1 inline h-3.5 w-3.5" /> L’identité est
            validée côté serveur avant l’accès au dashboard.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Metric({
  label,
  value,
  unit,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  icon: typeof Activity;
  tone: string;
}) {
  return (
    <div className="border border-zinc-800 bg-zinc-900 p-5">
      <div className="flex justify-between">
        <p className="text-[10px] font-bold uppercase tracking-[.17em] text-zinc-500">
          {label}
        </p>
        <Icon className={`h-4 w-4 ${tone}`} />
      </div>
      <p className="mt-8 font-mono text-3xl font-semibold text-zinc-100">
        {value}
        <span className="ml-1 text-sm text-zinc-500">{unit}</span>
      </p>
      <div className="mt-5 h-px bg-zinc-800" />
      <p className="mt-3 text-xs text-zinc-500">Télémétrie active</p>
    </div>
  );
}
const DONUT_COLORS = [
  "#a3e635",
  "#34d399",
  "#38bdf8",
  "#fbbf24",
  "#a78bfa",
  "#fb7185",
  "#fb923c",
];
function Donut({
  segments,
  size = 168,
  thickness = 24,
  centerLabel,
}: {
  segments: { label: string; value: number; color: string }[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
}) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let accumulated = 0;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label="Répartition de la consommation"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth={thickness}
      />
      {total > 0 &&
        segments.map(segment => {
          const fraction = segment.value / total;
          const element = (
            <circle
              key={segment.label}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth={thickness}
              strokeDasharray={`${fraction * circumference} ${circumference}`}
              strokeDashoffset={-accumulated * circumference}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          );
          accumulated += fraction;
          return element;
        })}
      {centerLabel && (
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          className="fill-slate-800 font-mono text-base"
        >
          {centerLabel}
        </text>
      )}
    </svg>
  );
}
function DonutLegend({
  segments,
  total,
}: {
  segments: { label: string; value: number; color: string }[];
  total: number;
}) {
  return (
    <div className="w-full max-w-[240px] space-y-2.5">
      {segments.map(segment => {
        const percent =
          total > 0 ? Math.round((segment.value / total) * 100) : 0;
        return (
          <div
            key={segment.label}
            className="flex items-center justify-between gap-3 font-mono text-xs"
          >
            <span className="flex items-center gap-2 text-slate-700">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: segment.color }}
              />
              {segment.label}
            </span>
            <span className="shrink-0 text-slate-600">
              {format(segment.value)} kWh{" "}
              <span className="text-slate-400">· {percent}%</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
function ConsumptionBreakdown({
  data,
}: {
  data: {
    mode?: string;
    consumption_daily?: { label: string; kwh: number }[] | null;
    consumption_weekly?: { label: string; date?: string; kwh: number }[] | null;
  };
}) {
  const toSegments = (entries: { label: string; kwh: number }[]) =>
    (entries ?? []).map((entry, index) => ({
      label: entry.label,
      value: Number(entry.kwh) || 0,
      color: DONUT_COLORS[index % DONUT_COLORS.length],
    }));
  const daily = toSegments(data.consumption_daily ?? []);
  const weekly = toSegments(data.consumption_weekly ?? []);
  const dailyTotal = daily.reduce((sum, entry) => sum + entry.value, 0);
  const weeklyTotal = weekly.reduce((sum, entry) => sum + entry.value, 0);
  const demo = data.mode === "DEMO";
  return (
    <section className="mt-4 grid gap-4 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-400">
              Répartition / 24 h
            </p>
            <h2 className="mt-2 text-xl font-semibold">
              Consommation journalière
            </h2>
          </div>
          {demo && (
            <span className="shrink-0 border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-bold tracking-[.14em] text-amber-700">
              DONNÉES DEMO
            </span>
          )}
        </div>
        {dailyTotal > 0 ? (
          <div className="mt-8 flex flex-col items-center gap-8 sm:flex-row sm:justify-around">
            <Donut segments={daily} centerLabel={`${format(dailyTotal)} kWh`} />
            <DonutLegend segments={daily} total={dailyTotal} />
          </div>
        ) : (
          <p className="mt-10 text-sm leading-6 text-slate-500">
            En attente de données de consommation sur 24 h…
          </p>
        )}
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-400">
              Répartition / 7 jours
            </p>
            <h2 className="mt-2 text-xl font-semibold">
              Consommation hebdomadaire
            </h2>
          </div>
          {demo && (
            <span className="shrink-0 border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-bold tracking-[.14em] text-amber-700">
              DONNÉES DEMO
            </span>
          )}
        </div>
        {weeklyTotal > 0 ? (
          <div className="mt-8 flex flex-col items-center gap-8 sm:flex-row sm:justify-around">
            <Donut
              segments={weekly}
              centerLabel={`${format(weeklyTotal)} kWh`}
            />
            <DonutLegend segments={weekly} total={weeklyTotal} />
          </div>
        ) : (
          <p className="mt-10 text-sm leading-6 text-slate-500">
            En attente de données de consommation sur 7 jours…
          </p>
        )}
      </div>
    </section>
  );
}
type ConsumptionPoint = { label: string; kwh: number; recharge?: string };
function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(value)));
  const d = value / p;
  const n = d <= 1 ? 1 : d <= 2 ? 2 : d <= 5 ? 5 : 10;
  return n * p;
}
function Sparkline({
  values,
  stroke,
  fill,
}: {
  values: number[];
  stroke: string;
  fill: string;
}) {
  const w = 96,
    h = 30,
    pad = 2;
  const max = Math.max(...values, 0.001);
  const points = values.map((value, index) => {
    const x = pad + (index / Math.max(values.length - 1, 1)) * (w - pad * 2);
    const y = h - pad - (value / max) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `M ${pad} ${h - pad} L ${points.join(" L ")} L ${w - pad} ${h - pad} Z`;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-8 w-28 opacity-90"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d={area} fill={fill} />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="1.7"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
function LiveChart({ series }: { series: ConsumptionPoint[] }) {
  const w = 720,
    h = 250,
    padL = 42,
    padR = 16,
    padT = 16,
    padB = 30;
  const iw = w - padL - padR,
    ih = h - padT - padB;
  const values = series.map(point => point.kwh);
  const max = niceCeil(Math.max(...values, 0.001));
  const n = Math.max(series.length, 2);
  const x = (index: number) => padL + (index / (n - 1)) * iw;
  const y = (value: number) => padT + ih - (value / max) * ih;
  const line = series
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${y(point.kwh).toFixed(1)}`
    )
    .join(" ");
  const baseline = (padT + ih).toFixed(1);
  const area = `${line} L ${x(series.length - 1).toFixed(1)} ${baseline} L ${padL} ${baseline} Z`;
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map(fraction => ({
    py: y(max * fraction),
    label: format(max * fraction, 1),
  }));
  const xStep = Math.max(1, Math.ceil(series.length / 7));
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label="Consommation en temps réel"
    >
      <defs>
        <linearGradient id="liveFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {gridLines.map(({ py, label }) => (
        <g key={`${label}-${py}`}>
          <line
            x1={padL}
            x2={w - padR}
            y1={py}
            y2={py}
            stroke="#e2e8f0"
            strokeWidth="1"
          />
          <text
            x={padL - 6}
            y={py + 3}
            textAnchor="end"
            className="fill-slate-400 text-[10px] font-mono"
          >
            {label}
          </text>
        </g>
      ))}
      {series.map(
        (point, index) =>
          index % xStep === 0 && (
            <text
              key={`${point.label}-${index}`}
              x={x(index)}
              y={padT + ih + 16}
              textAnchor="middle"
              className="fill-slate-400 text-[10px] font-mono"
            >
              {point.label}
            </text>
          )
      )}
      <path d={area} fill="url(#liveFill)" />
      <path
        d={line}
        fill="none"
        stroke="#10b981"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {series.map(
        (point, index) =>
          point.recharge && (
            <circle
              key={`recharge-${index}`}
              cx={x(index)}
              cy={y(point.kwh)}
              r="4"
              fill="#f59e0b"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          )
      )}
    </svg>
  );
}
function WeeklyBars({ series }: { series: ConsumptionPoint[] }) {
  const w = 460,
    h = 190,
    padL = 10,
    padR = 8,
    padT = 14,
    padB = 26;
  const iw = w - padL - padR,
    ih = h - padT - padB;
  const max = niceCeil(Math.max(...series.map(point => point.kwh), 0.001));
  const slot = iw / Math.max(series.length, 1);
  const barWidth = Math.max(14, slot - 10);
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label="Historique des 7 derniers jours"
    >
      {[0.25, 0.5, 0.75, 1].map(fraction => {
        const py = padT + ih - fraction * ih;
        const value = max * fraction;
        return (
          <g key={fraction}>
            <line
              x1={padL}
              x2={w - padR}
              y1={py}
              y2={py}
              stroke="#e2e8f0"
              strokeWidth="1"
            />
            <text
              x={padL + 2}
              y={py - 3}
              className="fill-slate-400 text-[9px] font-mono"
            >
              {format(value, 1)}
            </text>
          </g>
        );
      })}
      {series.map((point, index) => {
        const cx = padL + index * slot + slot / 2;
        const barH = (point.kwh / max) * ih;
        const py = padT + ih - barH;
        return (
          <g key={`${point.label}-${index}`}>
            <rect
              x={cx - barWidth / 2}
              y={py}
              width={barWidth}
              height={Math.max(barH, 2)}
              rx="4"
              fill="#10b981"
            />
            <text
              x={cx}
              y={py - 5}
              textAnchor="middle"
              className="fill-slate-600 text-[9px] font-mono"
            >
              {format(point.kwh, 1)}
            </text>
            <text
              x={cx}
              y={padT + ih + 16}
              textAnchor="middle"
              className="fill-slate-400 text-[9px] font-mono"
            >
              {point.label.slice(0, 3)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
function Gauge({
  ratio,
  center,
  sub,
}: {
  ratio: number;
  center: string;
  sub: string;
}) {
  const size = 190,
    cx = size / 2,
    cy = size * 0.55,
    r = 74;
  const clamp = Math.min(1, Math.max(0.02, ratio));
  const length = Math.PI * r;
  const path = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  return (
    <svg
      viewBox={`0 0 ${size} ${size * 0.62}`}
      className="mx-auto w-[190px]"
      role="img"
      aria-label="Prévision et solde"
    >
      <path
        d={path}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth="16"
        strokeLinecap="round"
      />
      <path
        d={path}
        fill="none"
        stroke="#34d399"
        strokeWidth="16"
        strokeLinecap="round"
        strokeDasharray={`${clamp * length} ${length}`}
      />
      <text
        x={cx}
        y={cy - 6}
        textAnchor="middle"
        className="fill-slate-800 text-2xl font-bold font-mono"
      >
        {center}
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        className="fill-slate-500 text-[11px]"
      >
        {sub}
      </text>
    </svg>
  );
}
const DASHBOARD_NAV = [
  { label: "Tableau de bord", icon: LayoutDashboard, active: true },
  { label: "Temps réel", icon: Activity, live: true },
  { label: "Consommation", icon: GaugeIcon },
  { label: "Historique", icon: History },
  { label: "Recharges", icon: RefreshCw },
  { label: "Factures", icon: FileText },
  { label: "Alertes", icon: BellRing },
  { label: "Appareils", icon: Cpu },
  { label: "Rapports", icon: BarChart3 },
  { label: "Paramètres", icon: Settings },
];
const NAV_TARGET: Record<string, string> = {
  "Tableau de bord": "dashboard-main",
  "Temps réel": "dashboard-main",
  Consommation: "dashboard-main",
  Historique: "panel-transactions",
  Recharges: "panel-recharges",
  Factures: "panel-transactions",
  Alertes: "panel-alertes",
  Appareils: "dashboard-main",
  Rapports: "dashboard-main",
  Paramètres: "panel-budget",
};
const ALERT_STYLE: Record<string, string> = {
  CRITIQUE: "border-red-200 bg-red-50 text-red-700",
  WARNING: "border-amber-200 bg-amber-50 text-amber-700",
  INFO: "border-sky-200 bg-sky-50 text-sky-700",
  SUCCESS: "border-emerald-200 bg-emerald-50 text-emerald-700",
};
function RealTimeChart({
  series,
  rate = 0,
}: {
  series: ConsumptionPoint[];
  rate?: number;
}) {
  const w = 720,
    h = 250,
    padL = 46,
    padR = 48,
    padT = 16,
    padB = 30;
  const iw = w - padL - padR,
    ih = h - padT - padB;
  const values = series.map(point => Number(point.kwh) || 0);
  const maxKwh = niceCeil(Math.max(...values, 0.001));
  const costs = rate > 0 ? values.map(v => v * rate) : [];
  const maxCost = niceCeil(Math.max(...costs, 0.001));
  const n = Math.max(series.length, 2);
  const x = (index: number) => padL + (index / (n - 1)) * iw;
  const yKwh = (value: number) => padT + ih - (value / maxKwh) * ih;
  const yCost = (value: number) => padT + ih - (value / maxCost) * ih;
  const energyLine = series
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${yKwh(Number(point.kwh) || 0).toFixed(1)}`
    )
    .join(" ");
  const baseline = (padT + ih).toFixed(1);
  const area = `${energyLine} L ${x(series.length - 1).toFixed(1)} ${baseline} L ${padL} ${baseline} Z`;
  const costLine =
    rate > 0
      ? costs
          .map(
            (value, index) =>
              `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${yCost(value).toFixed(1)}`
          )
          .join(" ")
      : "";
  const kwhTicks = [0.25, 0.5, 0.75, 1].map(fraction => ({
    py: yKwh(maxKwh * fraction),
    label: format(maxKwh * fraction, 1),
  }));
  const costTicks =
    rate > 0
      ? [0.25, 0.5, 0.75, 1].map(fraction => ({
          py: yCost(maxCost * fraction),
          label: format(maxCost * fraction, 2),
        }))
      : [];
  const xStep = Math.max(1, Math.ceil(series.length / 7));
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label="Consommation en temps réel"
    >
      <defs>
        <linearGradient id="liveFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {kwhTicks.map(({ py, label }) => (
        <g key={`k${label}-${py}`}>
          <line
            x1={padL}
            x2={w - padR}
            y1={py}
            y2={py}
            stroke="#e2e8f0"
            strokeWidth="1"
          />
          <text
            x={padL - 6}
            y={py + 3}
            textAnchor="end"
            className="fill-emerald-600 text-[10px] font-mono"
          >
            {label}
          </text>
        </g>
      ))}
      {costTicks.map(({ py, label }) => (
        <text
          key={`c${label}-${py}`}
          x={w - padR + 6}
          y={py + 3}
          textAnchor="start"
          className="fill-amber-600 text-[10px] font-mono"
        >
          $ {label}
        </text>
      ))}
      {series.map(
        (point, index) =>
          index % xStep === 0 && (
            <text
              key={`${point.label}-${index}`}
              x={x(index)}
              y={padT + ih + 16}
              textAnchor="middle"
              className="fill-slate-400 text-[10px] font-mono"
            >
              {point.label}
            </text>
          )
      )}
      <path d={area} fill="url(#liveFill)" />
      <path
        d={energyLine}
        fill="none"
        stroke="#10b981"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {costLine && (
        <path
          d={costLine}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="2"
          strokeDasharray="4 3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
      {series.map(
        (point, index) =>
          point.recharge && (
            <circle
              key={`recharge-${index}`}
              cx={x(index)}
              cy={yKwh(Number(point.kwh) || 0)}
              r="4"
              fill="#f59e0b"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          )
      )}
    </svg>
  );
}
function AssistantPanel({ token }: { token?: string | null }) {
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; text: string }[]
  >([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const messagesRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages, loading]);
  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setMessages(prev => [...prev, { role: "user", text: trimmed }]);
    setQuestion("");
    setLoading(true);
    setError("");
    try {
      const result = await askDjangoAssistant(trimmed, token);
      setMessages(prev => [
        ...prev,
        { role: "assistant", text: result.answer },
      ]);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "L'assistant est momentanément indisponible."
      );
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          text: "Votre agent IA est momentanément indisponible. Réessayez dans un instant.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };
  const suggestions = [
    "Quel est mon solde restant ?",
    "Combien de temps avant l'épuisement du crédit ?",
    "Voir mes anomalies",
    "Comment recharger mon compteur ?",
  ];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Bot className="h-5 w-5 text-emerald-600" /> Agent IA
        </h2>
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-bold text-emerald-700">
          CONTEXTUEL
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Posez une question sur votre compteur, solde, consommation ou anomalies.
      </p>
      <div
        ref={messagesRef}
        className="mt-3 flex h-56 flex-col gap-2 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50 p-3"
      >
        {messages.length === 0 && (
          <div className="flex flex-1 flex-wrap items-center justify-center gap-2">
            {suggestions.map(s => (
              <button
                key={s}
                disabled={loading}
                onClick={() => send(s)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex shrink-0 ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 ${m.role === "user" ? "bg-emerald-600 text-white" : "bg-white border border-slate-200 text-slate-700"}`}
            >
              {m.role === "assistant" ? (
                <div className="prose prose-sm max-w-none">
                  <Streamdown>{m.text}</Streamdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm">{m.text}</p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-400">
              <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" />
              Réflexion…
            </div>
          </div>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <form
        className="mt-3 flex gap-2"
        onSubmit={e => {
          e.preventDefault();
          send(question);
        }}
      >
        <Input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Écrivez votre question…"
          className="h-10"
        />
        <Button
          type="submit"
          disabled={!question.trim() || loading}
          className="h-10 bg-emerald-600 hover:bg-emerald-700"
        >
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
const PAY_NETWORKS = [
  { code: "AIRTEL_COD", label: "Airtel" },
  { code: "ORANGE_COD", label: "Orange" },
  { code: "VODACOM_MPESA_COD", label: "Vodacom" },
] as const;

function PaymentPanel({
  token,
  onDone,
  cdfPerUsd,
}: {
  token?: string | null;
  onDone: () => void;
  cdfPerUsd?: number;
}) {
  const rate = cdfPerUsd && cdfPerUsd > 0 ? cdfPerUsd : 2500;
  const [amount, setAmount] = useState(10000);
  const [mode, setMode] = useState<"pawapay" | "flutterwave" | null>(null);
  const [phone, setPhone] = useState("");
  const [network, setNetwork] = useState<string>("AIRTEL_COD");
  const [depositId, setDepositId] = useState<string | null>(null);
  const [phase, setPhase] = useState<
    "idle" | "pending" | "complete" | "failed"
  >("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{
    kind: "info" | "ok" | "error";
    text: string;
  } | null>(null);
  const [tokenValue, setTokenValue] = useState("");
  const [tokenBusy, setTokenBusy] = useState(false);

  const startPawaPay = async () => {
    if (!token || !amount) return;
    const cleanPhone = phone.replace(/\D/g, "");
    if (!cleanPhone) {
      setMessage({
        kind: "error",
        text: "Entrez votre numéro de téléphone mobile money (ex. 0993 456 789).",
      });
      return;
    }
    setBusy(true);
    setPhase("idle");
    setStatusMessage("");
    setMessage(null);
    setDepositId(null);
    const label = PAY_NETWORKS.find(n => n.code === network)?.label ?? network;
    try {
      const result = await initiatePayment(token, "pawapay", amount, {
        phoneNumber: cleanPhone,
        network,
      });
      if (result.accepted && result.deposit_id) {
        setDepositId(result.deposit_id);
        setPhase("pending");
        setMessage({
          kind: "info",
          text: `${label} : demande de dépôt envoyée. Autorisez le paiement sur VOTRE téléphone (prompt ${label}).`,
        });
      } else {
        setPhase("failed");
        setStatusMessage(
          result.detail || "Le dépôt n'a pas été accepté par PawaPay."
        );
      }
    } catch (cause) {
      setPhase("idle");
      setMessage({
        kind: "error",
        text: cause instanceof Error ? cause.message : "Paiement impossible.",
      });
    } finally {
      setBusy(false);
    }
  };

  // Polling du statut tant que le dépôt mobile money est en attente (réelle vérification côté PawaPay).
  useEffect(() => {
    if (phase !== "pending" || !depositId || !token) return;
    let stopped = false;
    const tick = async () => {
      try {
        const r = await getPawaPayStatus(token, depositId);
        if (stopped) return;
        if (r.applied) {
          setStatusMessage(
            r.customer_message || "Paiement confirmé par le réseau."
          );
          setPhase("complete");
          onDone();
        } else if (r.failed) {
          setStatusMessage(r.detail || "Paiement refusé par le réseau.");
          setPhase("failed");
        } else if (r.detail) {
          setMessage({ kind: "info", text: r.detail });
        }
      } catch (cause) {
        if (!stopped)
          setMessage({
            kind: "error",
            text:
              cause instanceof Error
                ? cause.message
                : "Vérification du statut impossible.",
          });
      }
    };
    tick();
    const timer = setInterval(tick, 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [phase, depositId, token]);

  const payCard = async () => {
    if (!token || !amount) return;
    setBusy(true);
    setPhase("idle");
    setStatusMessage("");
    setMessage(null);
    try {
      const result = await initiatePayment(token, "flutterwave", amount, {
        phoneNumber: phone.replace(/\D/g, "") || undefined,
      });
      if (result.link) window.open(result.link, "_blank", "noopener");
      setMessage({
        kind: "info",
        text:
          result.detail ||
          "Redirection vers Flutterwave… complétez le paiement sur la page sécurisée.",
      });
      onDone();
    } catch (cause) {
      setMessage({
        kind: "error",
        text: cause instanceof Error ? cause.message : "Paiement impossible.",
      });
    } finally {
      setBusy(false);
    }
  };
  const applyToken = async () => {
    if (!token || !tokenValue.trim()) return;
    setTokenBusy(true);
    setMessage(null);
    try {
      const result = await applyManualToken(token, tokenValue.trim());
      setMessage({
        kind: "ok",
        text: `Token appliqué : +${format(result.energy_kwh)} kWh (source ${result.source.replace(/_/g, " ")}). Nouveau solde ${format(result.balance_kwh)} kWh.`,
      });
      setTokenValue("");
      onDone();
    } catch (cause) {
      setMessage({
        kind: "error",
        text: cause instanceof Error ? cause.message : "Token invalide.",
      });
    } finally {
      setTokenBusy(false);
    }
  };
  const networkLabel =
    PAY_NETWORKS.find(n => n.code === network)?.label ?? network;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Wallet className="h-5 w-5 text-emerald-600" /> Recharger mon crédit
      </h2>
      <p className="mt-1 text-xs text-slate-500">
        Payez en ligne (mobile money local ou carte Visa) ou saisissez un token
        de revendeur. Taux affiché : 1 US$ = {format(rate, 0)} FC.
      </p>
      <div className="mt-3 flex items-center gap-2">
        {[5000, 10000, 20000, 50000].map(v => (
          <button
            key={v}
            onClick={() => setAmount(v)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${amount === v ? "border-emerald-600 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
          >
            {format(v, 0)} FC{" "}
            <span className="block text-[10px] font-normal opacity-70">
              = {format(v / rate, 2)} US$
            </span>
          </button>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          onClick={() => setMode(mode === "pawapay" ? null : "pawapay")}
          className={`flex items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold transition ${mode === "pawapay" ? "bg-gradient-to-br from-emerald-600 to-teal-600 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
        >
          <Smartphone className="h-4 w-4" /> Mobile Money (FC)
        </button>
        <button
          onClick={() => setMode(mode === "flutterwave" ? null : "flutterwave")}
          className={`flex items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold transition ${mode === "flutterwave" ? "bg-gradient-to-br from-violet-600 to-purple-600 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
        >
          <CreditCard className="h-4 w-4" /> Carte Visa (US$)
        </button>
      </div>

      {mode === "pawapay" && phase !== "pending" && phase !== "complete" && (
        <div className="mt-3 rounded-xl border border-slate-100 p-3">
          <Label className="text-xs">
            Numéro mobile money (Airtel / Orange / Vodacom)
          </Label>
          <Input
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="Ex. 0993 456 789"
            className="mt-1 h-10"
            inputMode="tel"
          />
          <Label className="mt-3 text-xs">Réseau</Label>
          <select
            value={network}
            onChange={e => setNetwork(e.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm"
          >
            {PAY_NETWORKS.map(n => (
              <option key={n.code} value={n.code}>
                {n.label}
              </option>
            ))}
          </select>
          <p className="mt-2 text-[11px] leading-4 text-slate-400">
            Après validation, l'opérateur vous enverra un prompt USSD sur votre
            téléphone : vous y saisirez votre PIN mobile money. Le paiement sera
            confirmé par le réseau.
          </p>
          <Button
            type="button"
            onClick={startPawaPay}
            disabled={busy}
            className="mt-3 w-full bg-emerald-600 hover:bg-emerald-700"
          >
            {busy
              ? "Envoi…"
              : `Payer ${format(amount, 0)} FC via ${networkLabel}`}
          </Button>
        </div>
      )}

      {mode === "flutterwave" && (
        <div className="mt-3 rounded-xl border border-slate-100 p-3">
          <p className="text-xs text-slate-500">
            Vous serez redirigé vers la page de paiement sécurisée Flutterwave
            pour saisir votre carte Visa et valider le paiement.
          </p>
          <Button
            type="button"
            onClick={payCard}
            disabled={busy}
            className="mt-2 w-full bg-violet-600 hover:bg-violet-700"
          >
            {busy
              ? "Redirection…"
              : `Payer ${format(amount / rate, 2)} US$ en carte`}
          </Button>
        </div>
      )}

      {mode === "pawapay" && phase === "pending" && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-sky-100 bg-sky-50 p-3 text-xs">
          <Loader2 className="h-4 w-4 animate-spin text-sky-600" />
          <div>
            <p className="font-semibold text-slate-700">
              En attente de votre autorisation…
            </p>
            <p className="mt-1 text-slate-500">
              Nous vérifions le statut du dépôt. Validez le paiement sur votre
              téléphone (PIN mobile money).
              {depositId ? ` Réf. ${depositId.slice(-8)}` : ""}
            </p>
          </div>
        </div>
      )}

      {phase === "complete" && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-700">
          <p className="font-semibold">Paiement effectué avec succès ✅</p>
          {statusMessage && <p className="mt-1">{statusMessage}</p>}
          <p className="mt-1 text-emerald-600">
            Le crédit a été ajouté à votre compteur.
          </p>
        </div>
      )}
      {phase === "failed" && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          <p className="font-semibold">Paiement refusé</p>
          {statusMessage && <p className="mt-1">{statusMessage}</p>}
        </div>
      )}

      {message && (
        <p
          className={`mt-3 rounded-lg border p-2 text-xs leading-5 ${message.kind === "ok" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : message.kind === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-sky-200 bg-sky-50 text-sky-700"}`}
        >
          {message.text}
        </p>
      )}
      <div className="mt-4 border-t border-slate-100 pt-4">
        <p className="text-xs font-semibold text-slate-600">
          Acheter un token chez un revendeur
        </p>
        <div className="mt-2 flex gap-2">
          <Input
            value={tokenValue}
            onChange={e => setTokenValue(e.target.value)}
            placeholder="Coller le token de 20 chiffres…"
            className="h-10 font-mono"
          />
          <Button
            type="button"
            disabled={tokenBusy || !tokenValue.trim()}
            onClick={applyToken}
            className="h-10 bg-slate-900 hover:bg-slate-800"
          >
            Appliquer
          </Button>
        </div>
      </div>
    </div>
  );
}
function TransactionsPanel({
  data,
  token,
}: {
  data: DjangoSnapshot;
  token?: string | null;
}) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const download = async (id: string) => {
    if (!token) return;
    setDownloading(id);
    try {
      const blob = await downloadReceiptPdf(token, id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `recu-${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      alert(
        cause instanceof Error ? cause.message : "Téléchargement impossible."
      );
    } finally {
      setDownloading(null);
    }
  };
  const recharges = data.recharges ?? [];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <History className="h-5 w-5 text-emerald-600" /> Transactions /
          Recharges
        </h2>
        <span className="text-xs text-slate-400">
          {recharges.length} opérations
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {recharges.length === 0 && (
          <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
            Aucune recharge enregistrée.
          </p>
        )}
        {recharges.map(recharge => (
          <div
            key={recharge.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 p-3"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${recharge.source === "SAISIE_MANUELLE" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}
                >
                  {recharge.source === "SAISIE_MANUELLE"
                    ? "REVENDEUR"
                    : "PAIEMENT EN LIGNE"}
                </span>
                <span className="text-xs text-slate-500">
                  {recharge.applied_at
                    ? new Date(recharge.applied_at).toLocaleDateString("fr-FR")
                    : ""}
                </span>
              </div>
              <p className="mt-1 font-mono text-sm font-semibold text-slate-800">
                +{format(recharge.energy_kwh)} kWh{" "}
                {recharge.status ? `· ${recharge.status}` : ""}
              </p>
            </div>
            <button
              onClick={() => download(recharge.id)}
              disabled={downloading === recharge.id}
              className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              <Download className="h-3.5 w-3.5" />{" "}
              {downloading === recharge.id ? "…" : "Reçu PDF"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
function BudgetPanel({
  data,
  token,
  onDone,
}: {
  data: DjangoSnapshot;
  token?: string | null;
  onDone: () => void;
}) {
  const limit = data.budget?.limit_kwh || 0;
  const used = data.budget?.used_kwh || 0;
  const percent =
    limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const over = limit > 0 && used > limit;
  const [value, setValue] = useState(String(limit || ""));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null
  );
  const save = async () => {
    if (!token) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setMsg({ kind: "error", text: "Plafond invalide." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const result = await updateBudget(token, parsed);
      setMsg({
        kind: "ok",
        text: `Plafond défini à ${format(result.limit_kwh)} kWh.`,
      });
      onDone();
    } catch (cause) {
      setMsg({
        kind: "error",
        text:
          cause instanceof Error ? cause.message : "Mise à jour impossible.",
      });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheck className="h-5 w-5 text-emerald-600" /> Mode budget
        </h2>
        {over && (
          <span className="rounded-full bg-red-100 px-2.5 py-1 text-[10px] font-bold text-red-700">
            DÉPASSÉ
          </span>
        )}
      </div>
      <div className="mt-3">
        <div className="flex justify-between text-xs text-slate-500">
          <span>{format(used)} kWh utilisés</span>
          <span>{limit > 0 ? `${percent}% du plafond` : "aucun plafond"}</span>
        </div>
        <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all ${over ? "bg-red-500" : percent >= 80 ? "bg-amber-500" : "bg-emerald-500"}`}
            style={{ width: `${percent}%` }}
          />
        </div>
        {over ? (
          <p className="mt-2 text-xs text-red-600">
            Vous avez dépassé votre plafond de consommation.
          </p>
        ) : percent >= 80 ? (
          <p className="mt-2 text-xs text-amber-600">
            Attention, vous approchez de votre plafond.
          </p>
        ) : (
          <p className="mt-2 text-xs text-slate-500">
            Vous serez alerté en cas de dépassement.
          </p>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <Input
          value={value}
          onChange={e => setValue(e.target.value)}
          type="number"
          min="1"
          placeholder="Plafond (kWh)"
          className="h-10"
        />
        <Button
          type="button"
          disabled={busy}
          onClick={save}
          className="h-10 bg-emerald-600 hover:bg-emerald-700"
        >
          Définir
        </Button>
      </div>
      {msg && (
        <p
          className={`mt-2 text-xs ${msg.kind === "ok" ? "text-emerald-600" : "text-red-600"}`}
        >
          {msg.text}
        </p>
      )}
    </div>
  );
}
function Dashboard({
  subscriber,
  exit,
  preview = false,
}: {
  subscriber: Subscriber;
  exit: () => void;
  preview?: boolean;
}) {
  const { data, isLoading, error, refresh } = useDjangoDashboard(
    subscriber.accessToken,
    preview
  );
  const [confirm, setConfirm] = useState(false);
  const [commandError, setCommandError] = useState("");
  const [submittingCommand, setSubmittingCommand] = useState(false);
  const [optimisticCommand, setOptimisticCommand] = useState<
    "ON" | "OFF" | null
  >(null);
  const [search, setSearch] = useState("");
  const [showAlerts, setShowAlerts] = useState(false);
  useEffect(() => {
    if (!data?.relay_command) setOptimisticCommand(null);
  }, [data?.relay_command]);
  if (isLoading || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6 text-center font-mono text-sm text-slate-500">
        {error ? (
          <div>
            <AlertTriangle className="mx-auto mb-3 text-amber-500" />
            <p>{error.message}</p>
            <Button className="mt-5" variant="outline" onClick={exit}>
              Retour à l’accueil
            </Button>
          </div>
        ) : (
          "INITIALISATION DU POSTE DE CONTRÔLE…"
        )}
      </div>
    );
  }
  const relayOn = data.meter.relay_status;
  const pending =
    Boolean(optimisticCommand) || data.relay_command?.status === "PENDING";
  const demoTag = data.mode === "DEMO";
  const t = data.telemetry;
  const spark = (arr: { kwh: number }[] | null | undefined) =>
    (arr ?? []).map(item => Number(item.kwh || 0));
  const daily = (data.consumption_daily ?? []).reduce(
    (sum, item) => sum + Number(item.kwh || 0),
    0
  );
  const weekly = (data.consumption_weekly ?? []).reduce(
    (sum, item) => sum + Number(item.kwh || 0),
    0
  );
  const daysLeft = data.estimate_hours / 24;
  const avgDaily = weekly / 7;
  const balanceRatio = Math.min(
    1,
    (data.balance.kwh ?? 0) / Math.max(data.budget.limit_kwh ?? 1, 1)
  );
  const online = data.meter.device_status === "ONLINE";
  const signal = data.meter.signal_strength ?? 0;
  const powerKw = Number(t.power) / 1000;
  const submitRelay = async () => {
    setCommandError("");
    if (!subscriber.accessToken) {
      setCommandError(
        "La prévisualisation ne permet pas d’envoyer une commande relais."
      );
      return;
    }
    setSubmittingCommand(true);
    try {
      const command = await requestRelayCommand(
        subscriber.accessToken,
        relayOn ? "OFF" : "ON"
      );
      setOptimisticCommand(command.desired_state);
      setConfirm(false);
    } catch (cause) {
      setCommandError(
        cause instanceof Error ? cause.message : "Commande relais impossible."
      );
    } finally {
      setSubmittingCommand(false);
    }
  };
  const kpis = [
    {
      label: "Énergie consommée",
      value: format(daily),
      unit: "kWh",
      sub: "Aujourd'hui",
      icon: Bolt,
      gradient: "from-emerald-600 to-teal-500",
      spark: spark(data.consumption_daily),
    },
    {
      label: "Puissance actuelle",
      value: format(powerKw),
      unit: "kW",
      sub: "En temps réel",
      icon: Activity,
      gradient: "from-sky-600 to-blue-500",
      spark: spark(data.consumption),
    },
    {
      label: "Tension",
      value: format(t.voltage),
      unit: "V",
      sub: "Stable",
      icon: GaugeIcon,
      gradient: "from-orange-500 to-amber-400",
      spark: spark(data.consumption),
    },
    {
      label: "Courant",
      value: format(t.current),
      unit: "A",
      sub: "En temps réel",
      icon: Zap,
      gradient: "from-violet-600 to-purple-500",
      spark: spark(data.consumption),
    },
    {
      label: "Coût estimé aujourd'hui",
      value: format(data.balance.usd),
      unit: "$",
      sub: "Basé sur votre tarif",
      icon: CircleDollarSign,
      gradient: "from-emerald-500 to-lime-500",
      spark: spark(data.consumption_weekly),
    },
  ];
  const alerts = data.alerts ?? [];
  const peakHour = (data.consumption ?? []).reduce<{
    label: string;
    kwh: number;
  } | null>((max, c) => (Number(c.kwh) > (max?.kwh ?? 0) ? c : max), null);
  const balanceIsLow = (data.balance.kwh ?? 0) < 5;
  const scrollToPanel = (id: string) =>
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  const searchResults = (() => {
    const q = search.trim().toLowerCase();
    if (!q)
      return [] as {
        type: string;
        title: string;
        sub: string;
        target: string;
      }[];
    const out: { type: string; title: string; sub: string; target: string }[] =
      [];
    for (const r of data.recharges ?? []) {
      const srcLabel =
        r.source === "SAISIE_MANUELLE" ? "Revendeur" : "Paiement en ligne";
      const date = r.applied_at
        ? new Date(r.applied_at).toLocaleDateString("fr-FR")
        : "";
      const hay =
        `${srcLabel} ${r.status ?? ""} ${r.energy_kwh} ${date} recharge facture token`.toLowerCase();
      if (hay.includes(q))
        out.push({
          type: "Recharge",
          title: `+${format(r.energy_kwh)} kWh (${srcLabel})`,
          sub: `${date} · ${r.status ?? "appliqué"}`,
          target: "panel-transactions",
        });
    }
    for (const a of data.alerts ?? []) {
      const kind = (a.kind ?? "").replace(/_/g, " ");
      const hay = `${kind} ${a.message ?? ""}`.toLowerCase();
      if (hay.includes(q))
        out.push({
          type: "Alerte",
          title: kind,
          sub: a.message ?? "",
          target: "panel-alertes",
        });
    }
    return out.slice(0, 8);
  })();
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col bg-slate-900 lg:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          <img
            src={assets.logo}
            alt="Virunga Energies"
            className="h-10 w-10 shrink-0 rounded-full object-contain"
          />
          <div className="min-w-0">
            <p className="truncate text-sm font-black tracking-[.16em] text-white">
              VIRUNGA
            </p>
            <p className="text-[10px] tracking-[.14em] text-slate-400">
              COMPTEUR INTELLIGENT
            </p>
          </div>
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {DASHBOARD_NAV.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                onClick={() =>
                  scrollToPanel(NAV_TARGET[item.label] ?? "dashboard-main")
                }
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${item.active ? "bg-emerald-600 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1 text-left">{item.label}</span>
                {item.live && (
                  <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-emerald-300">
                    LIVE
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="mx-3 mb-5 rounded-xl bg-slate-800/70 p-4 text-center">
          <p className="text-xs font-semibold text-white">Besoin d'aide ?</p>
          <p className="mt-1 text-[11px] leading-4 text-slate-400">
            Notre équipe support est disponible 24h/24 et 7j/7 en cas de besoin.
          </p>
        </div>
      </aside>
      {/* Main */}
      <div className="lg:pl-64">
        {/* Top bar */}
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-background/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-4 py-3.5 sm:px-5 lg:px-8">
            <div className="min-w-0">
              <p className="truncate text-base font-bold">
                Bonjour, {subscriber.firstName} {subscriber.lastName}{" "}
                <span>👋</span>
              </p>
              <p className="truncate text-xs text-slate-500">
                Voici un aperçu, en temps réel, de votre consommation.
              </p>
            </div>
            <div className="relative hidden flex-1 max-w-md md:block">
              <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-400 focus-within:border-emerald-400 focus-within:bg-white">
                <Search className="h-4 w-4 shrink-0" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Rechercher une recharge, une alerte…"
                  className="w-full bg-transparent text-slate-700 outline-none placeholder:text-slate-400"
                />
                {search && (
                  <button
                    aria-label="Effacer la recherche"
                    onClick={() => setSearch("")}
                    className="shrink-0 text-slate-400 hover:text-slate-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              {search.trim() && (
                <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
                  {searchResults.length === 0 ? (
                    <p className="px-4 py-3 text-xs text-slate-400">
                      Aucun résultat pour « {search.trim()} ».
                    </p>
                  ) : (
                    searchResults.map((r, i) => (
                      <button
                        key={`${r.type}-${i}`}
                        onClick={() => {
                          scrollToPanel(r.target);
                          setSearch("");
                        }}
                        className="flex w-full items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5 text-left hover:bg-slate-50"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-slate-800">
                            {r.title}
                          </span>
                          <span className="block truncate text-[11px] text-slate-500">
                            {r.sub}
                          </span>
                        </span>
                        <span className="shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">
                          {r.type}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold sm:flex ${online ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${online ? "bg-emerald-500" : "bg-red-500"}`}
                />
                {online ? "En ligne" : "Déconnecté"}
              </span>
              <div className="relative">
                <button
                  aria-label="Notifications"
                  onClick={() => setShowAlerts(v => !v)}
                  className="relative rounded-full border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
                >
                  <BellRing className="h-4 w-4" />
                  {alerts.length > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                      {alerts.length}
                    </span>
                  )}
                </button>
                {showAlerts && (
                  <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
                    <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
                      <p className="text-sm font-semibold text-slate-800">
                        Notifications
                      </p>
                      {alerts.length > 0 && (
                        <button
                          onClick={() => {
                            scrollToPanel("panel-alertes");
                            setShowAlerts(false);
                          }}
                          className="text-[11px] font-medium text-emerald-700 hover:underline"
                        >
                          Voir tout
                        </button>
                      )}
                    </div>
                    <div className="max-h-72 overflow-y-auto">
                      {alerts.length === 0 && (
                        <p className="px-4 py-6 text-center text-xs text-slate-400">
                          Aucune notification.
                        </p>
                      )}
                      {alerts.map((alert, index) => (
                        <div
                          key={`${alert.kind}-${index}`}
                          className="flex items-start gap-2 border-b border-slate-100 px-4 py-3"
                        >
                          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-slate-800">
                              {alert.kind.replace(/_/g, " ")}
                            </p>
                            <p className="mt-0.5 text-[11px] leading-4 text-slate-500">
                              {alert.message}
                            </p>
                            <p className="mt-1 text-[10px] text-slate-400">
                              {alert.created_at
                                ? new Date(alert.created_at).toLocaleString(
                                    "fr-FR"
                                  )
                                : ""}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <ThemeToggle />
              <Button
                variant="outline"
                className="h-9 border-slate-200 bg-white text-slate-600"
                onClick={exit}
              >
                <LogOut className="mr-1 h-3.5 w-3.5" /> Se déconnecter
              </Button>
            </div>
          </div>
        </header>
        <main
          id="dashboard-main"
          className="mx-auto max-w-[1500px] px-4 py-6 sm:px-5 lg:px-8"
        >
          <div className="mb-5 flex flex-col justify-between gap-2 md:flex-row md:items-end">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                État du compteur et crédit prépayé
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                Tableau de bord abonné · actualisation toutes les 5 secondes ·{" "}
                {demoTag ? "données de démonstration" : "données réelles"}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
              <span className="font-mono">Flux signé / HMAC</span>
            </div>
          </div>
          {/* KPI cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
            {kpis.map(kpi => {
              const Icon = kpi.icon;
              return (
                <div
                  key={kpi.label}
                  className={`relative overflow-hidden rounded-2xl bg-gradient-to-br ${kpi.gradient} p-4 text-white shadow-lg shadow-slate-200`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[10px] font-bold uppercase tracking-[.16em] text-white/80">
                      {kpi.label}
                    </p>
                    <Icon className="h-4 w-4 text-white/90" />
                  </div>
                  <p className="mt-4 font-mono text-2xl font-semibold">
                    {kpi.value}
                    <span className="ml-1 text-sm text-white/80">
                      {kpi.unit}
                    </span>
                  </p>
                  <div className="mt-3 flex items-end justify-between gap-2">
                    <p className="text-[11px] text-white/80">{kpi.sub}</p>
                    <Sparkline
                      values={kpi.spark}
                      stroke="#ffffff"
                      fill="rgba(255,255,255,0.25)"
                    />
                  </div>
                </div>
              );
            })}
          </div>
          {/* Dispatch row */}
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            {/* Live chart */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-400">
                    Aujourd'hui · 5 min
                  </p>
                  <h2 className="mt-1 flex items-center gap-2 text-lg font-semibold">
                    Consommation en temps réel{" "}
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">
                      LIVE
                    </span>
                  </h2>
                </div>
                <div className="flex flex-wrap justify-end gap-2 text-[11px] font-medium text-slate-500">
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />{" "}
                    Énergie
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-500" />{" "}
                    Recharge
                  </span>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-slate-50 p-2 text-center">
                  <p className="text-[10px] text-slate-400">Puissance</p>
                  <p className="font-mono text-sm font-semibold text-slate-700">
                    {format(powerKw)} kW
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2 text-center">
                  <p className="text-[10px] text-slate-400">Tension</p>
                  <p className="font-mono text-sm font-semibold text-slate-700">
                    {format(t.voltage)} V
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2 text-center">
                  <p className="text-[10px] text-slate-400">Courant</p>
                  <p className="font-mono text-sm font-semibold text-slate-700">
                    {format(t.current)} A
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <LiveChart series={data.consumption} />
              </div>
            </div>
            {/* Right column: états + alertes */}
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">État du compteur</h2>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${online ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}
                  >
                    {online ? "En ligne" : "Hors ligne"}
                  </span>
                </div>
                <div className="mt-4 flex items-center gap-4">
                  <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-slate-800 to-slate-900 text-white">
                    <Power className="h-8 w-8" />
                    <span className="absolute bottom-1.5 right-1.5 h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500">ID Compteur</p>
                    <p className="font-mono text-sm font-semibold">
                      {data.meter.id}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Mode :{" "}
                      <span className="font-medium text-slate-700">
                        Prépayé
                      </span>
                    </p>
                    <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                      <Clock3 className="h-3 w-3" /> Dernière communication il y
                      a 5 s
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Wifi className="h-3.5 w-3.5 text-emerald-600" /> Signal{" "}
                    {signal}%
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5 text-slate-400" />{" "}
                    {data.meter.firmware_version}
                  </span>
                </div>
                {/* Relay control (kept for the project contract) */}
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                        Relais / Alimentation
                      </p>
                      <p
                        className={`mt-0.5 text-sm font-semibold ${relayOn ? "text-emerald-700" : "text-red-600"}`}
                      >
                        {pending
                          ? "COMMANDE EN ATTENTE"
                          : relayOn
                            ? "Alimentation active"
                            : "Alimentation coupée"}
                      </p>
                    </div>
                    <Button
                      disabled={submittingCommand || pending}
                      onClick={() => setConfirm(true)}
                      className="h-9 bg-red-600 hover:bg-red-700"
                      variant={relayOn ? "default" : "secondary"}
                    >
                      {relayOn ? "Demander l’isolement" : "Rétablir le courant"}
                    </Button>
                  </div>
                  {commandError && (
                    <p className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                      {commandError}
                    </p>
                  )}
                </div>
              </div>
              <div
                id="panel-alertes"
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Alertes récentes</h2>
                  <span className="text-xs font-medium text-slate-400">
                    Voir tout
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {alerts.length === 0 && (
                    <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                      Aucune alerte récente.
                    </p>
                  )}
                  {alerts.map((alert, index) => (
                    <div
                      key={`${alert.kind}-${index}`}
                      className={`flex items-start justify-between gap-2 rounded-lg border p-3 ${ALERT_STYLE[alert.severity] ?? ALERT_STYLE.INFO}`}
                    >
                      <div className="flex items-start gap-2">
                        {alert.severity === "WARNING" ? (
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        ) : (
                          <Info className="mt-0.5 h-4 w-4 shrink-0" />
                        )}
                        <div>
                          <p className="text-xs font-semibold">
                            {alert.kind.replace(/_/g, " ")}
                          </p>
                          <p className="mt-0.5 text-[11px] leading-4 opacity-90">
                            {alert.message}
                          </p>
                        </div>
                      </div>
                      <span className="shrink-0 text-[10px] opacity-70">
                        {alert.created_at
                          ? new Date(alert.created_at).toLocaleTimeString(
                              "fr-FR",
                              { hour: "2-digit", minute: "2-digit" }
                            )
                          : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          {/* Donuts + Historique + Prévision */}
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <ConsumptionBreakdown data={data} />
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-400">
                  Historique
                </p>
                <h2 className="mt-1 text-lg font-semibold">7 derniers jours</h2>
                <div className="mt-4">
                  <WeeklyBars series={data.consumption_weekly ?? []} />
                </div>
                <button className="mt-2 text-xs font-semibold text-emerald-700 underline underline-offset-4">
                  Voir le rapport
                </button>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-400">
                  Prévision
                </p>
                <h2 className="mt-1 text-lg font-semibold">
                  Prévision & Solde
                </h2>
                <div className="mt-3">
                  <Gauge
                    ratio={balanceRatio}
                    center={`~${format(daysLeft, 1)} j`}
                    sub="avant l'épuisement du solde"
                  />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  Consommation moyenne{" "}
                  <span className="font-mono font-semibold text-slate-700">
                    {format(avgDaily, 1)} kWh/jour
                  </span>
                </p>
              </div>
            </div>
          </div>
          {/* Actions rapides */}
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold">Actions rapides</h2>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                {
                  label: "Recharger",
                  sub: "Ajouter des kWh",
                  icon: RefreshCw,
                  tone: "bg-emerald-100 text-emerald-700",
                },
                {
                  label: "Historique",
                  sub: "Voir les données",
                  icon: History,
                  tone: "bg-sky-100 text-sky-700",
                },
                {
                  label: "Factures",
                  sub: "Télécharger PDF",
                  icon: FileText,
                  tone: "bg-violet-100 text-violet-700",
                },
                {
                  label: "Paramètres",
                  sub: "Gérer le compte",
                  icon: Settings,
                  tone: "bg-amber-100 text-amber-700",
                },
              ].map(action => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.label}
                    onClick={() =>
                      scrollToPanel(
                        action.label === "Recharger"
                          ? "panel-recharges"
                          : action.label === "Historique" ||
                              action.label === "Factures"
                            ? "panel-transactions"
                            : "panel-budget"
                      )
                    }
                    className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-left hover:bg-slate-50"
                  >
                    <span
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${action.tone}`}
                    >
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="min-w-0">
                      <p className="truncate text-sm font-semibold">
                        {action.label}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        {action.sub}
                      </p>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          {/* Rechargement, transactions, budget & agent IA */}
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div id="panel-recharges">
              <PaymentPanel
                token={subscriber.accessToken}
                onDone={refresh}
                cdfPerUsd={data.cdf_per_usd}
              />
            </div>
            <div id="panel-transactions">
              <TransactionsPanel data={data} token={subscriber.accessToken} />
            </div>
            <div id="panel-budget">
              <BudgetPanel
                data={data}
                token={subscriber.accessToken}
                onDone={refresh}
              />
            </div>
            <div id="panel-assistant">
              <AssistantPanel token={subscriber.accessToken} />
            </div>
          </div>
          {/* Footer : technologies + statut */}
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-500">
                Conseils pour économiser
              </h3>
              <div className="mt-3 space-y-2 text-xs leading-5 text-slate-600">
                <p className="flex items-start gap-2">
                  <Leaf className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  Votre pic de consommation quotidien apparaît vers{" "}
                  <b>{peakHour?.label ?? "—"}</b> (
                  {peakHour ? `${format(peakHour.kwh, 2)} kWh` : "n/a"}).
                </p>
                <p className="flex items-start gap-2">
                  <TrendingUp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  Consommation moyenne : <b>{format(avgDaily, 1)} kWh/jour</b>.
                </p>
                {balanceIsLow && (
                  <p className="flex items-start gap-2">
                    <Bolt className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                    Solde faible ({format(data.balance.kwh, 1)} kWh) : pensez à
                    recharger.
                  </p>
                )}
                <p className="flex items-start gap-2">
                  <Bolt className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  Le relais{" "}
                  {relayOn
                    ? "est actif : votre compteur fonctionne normalement."
                    : "est coupé : rétablissez le solde pour reprendre la fourniture."}
                </p>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-500">
                Statut du système
              </h3>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <span className="flex items-center gap-1.5 text-slate-600">
                  <CircleCheck className="h-3.5 w-3.5 text-emerald-600" />{" "}
                  Disponibilité 99,8%
                </span>
                <span className="flex items-center gap-1.5 text-slate-600">
                  <RefreshCw className="h-3.5 w-3.5 text-emerald-600" /> Mise à
                  jour : 5 s
                </span>
                <span className="flex items-center gap-1.5 text-slate-600">
                  <Timer className="h-3.5 w-3.5 text-emerald-600" /> Latence 39
                  ms
                </span>
                <span className="flex items-center gap-1.5 text-slate-600">
                  <LockKeyhole className="h-3.5 w-3.5 text-emerald-600" />{" "}
                  Sécurité chiffrée
                </span>
              </div>
            </div>
          </div>
          <p className="mt-6 pb-4 text-center text-xs text-slate-400">
            © 2026 Virunga Energies · Compteur intelligent v1.0.0 · Sécurisé
            avec SSL
          </p>
        </main>
      </div>
      {/* Confirmation dialog for the relay command */}
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="max-w-md rounded-xl border-slate-200 p-0">
          <div className="p-6">
            <DialogHeader>
              <DialogTitle className="text-xl font-bold">
                Confirmer la demande relais
              </DialogTitle>
              <DialogDescription>
                Cette action enverra une commande au compteur intelligent.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-6">
              <Button
                disabled={submittingCommand}
                onClick={submitRelay}
                className="bg-red-600 hover:bg-red-700"
              >
                Confirmer l’isolement
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
export default function Home() {
  const previewMode = import.meta.env.DEV
    ? new URLSearchParams(window.location.search).get("ui")
    : null;
  const previewDashboard = previewMode === "dashboard";
  const [open, setOpen] = useState(previewMode === "login");
  const [subscriber, setSubscriber] = useState<Subscriber | null>(
    previewDashboard
      ? {
          firstName: "Amani",
          lastName: "Kambale",
          meterCode: "12345678901234567890",
        }
      : null
  );
  const authenticate = async (input: Subscriber) => {
    const session = await loginSubscriber(input);
    setSubscriber({
      ...input,
      firstName: session.subscriber.firstName,
      lastName: session.subscriber.lastName,
      meterCode: input.meterCode,
      accessToken: session.accessToken,
    });
  };
  const leave = () => {
    clearSubscriberSession();
    setSubscriber(null);
  };
  return (
    <>
      {subscriber ? (
        <Dashboard
          subscriber={subscriber}
          preview={previewDashboard}
          exit={leave}
        />
      ) : (
        <PublicView login={() => setOpen(true)} />
      )}
      <Login open={open} setOpen={setOpen} submit={authenticate} />
    </>
  );
}
