import { Activity, BadgeCheck, ShieldCheck, Stethoscope } from "lucide-react";

import { AuthActions } from "./auth-actions";

type LoginViewProps = {
  keycloakIssuer: string;
  clientId: string;
};

export function LoginView({ keycloakIssuer, clientId }: LoginViewProps) {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f7faf9]">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 h-[34rem] w-[34rem] rounded-full bg-teal-100/70 blur-3xl" />
        <div className="absolute -bottom-48 right-0 h-[34rem] w-[34rem] rounded-full bg-emerald-100/70 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(#155e4b10_1px,transparent_1px)] [background-size:22px_22px]" />
      </div>

      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-5 py-6 sm:px-8 lg:px-12">
        <header className="flex items-center justify-between">
          <a aria-label="MediGest, inicio" className="inline-flex items-center gap-3" href="/">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-800 text-white shadow-sm">
              <Stethoscope aria-hidden="true" size={23} />
            </span>
            <span>
              <span className="block text-lg font-bold tracking-tight text-ink">
                MediGest
              </span>
              <span className="block text-[11px] font-medium tracking-wide text-muted-foreground">
                GESTIÓN DE ATENCIÓN
              </span>
            </span>
          </a>
          <span className="hidden items-center gap-2 text-sm text-slate-600 sm:flex">
            <ShieldCheck aria-hidden="true" className="text-teal-700" size={17} />
            Acceso protegido
          </span>
        </header>

        <div className="grid flex-1 items-center gap-12 py-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-20">
          <section className="mx-auto max-w-xl lg:mx-0">
            <span className="inline-flex items-center gap-2 rounded-full border border-teal-700/10 bg-white/80 px-3.5 py-2 text-xs font-semibold text-teal-800 shadow-sm">
              <Activity aria-hidden="true" size={15} />
              Una experiencia clara para cada equipo
            </span>
            <h1 className="mt-7 text-4xl font-semibold leading-[1.12] tracking-tight text-ink sm:text-5xl lg:text-6xl">
              La atención en salud,
              <span className="block text-teal-700">mejor conectada.</span>
            </h1>
            <p className="mt-6 max-w-lg text-base leading-7 text-slate-600 sm:text-lg sm:leading-8">
              Un espacio de trabajo seguro para los equipos de consultorios y
              centros médicos. Ingresa con las credenciales de tu institución.
            </p>
            <ul className="mt-8 grid gap-4 text-sm text-slate-700 sm:grid-cols-2">
              <li className="flex items-center gap-3">
                <BadgeCheck aria-hidden="true" className="shrink-0 text-teal-700" size={19} />
                Acceso según tu rol
              </li>
              <li className="flex items-center gap-3">
                <ShieldCheck aria-hidden="true" className="shrink-0 text-teal-700" size={19} />
                Sesión protegida
              </li>
            </ul>
          </section>

          <section
            aria-labelledby="login-title"
            className="mx-auto w-full max-w-md rounded-3xl border border-white/80 bg-white/90 p-6 shadow-[0_24px_80px_-34px_rgba(16,65,56,0.28)] backdrop-blur sm:p-9"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-mint text-teal-800">
              <Stethoscope aria-hidden="true" size={23} />
            </span>
            <h2 className="mt-6 text-2xl font-semibold tracking-tight text-ink" id="login-title">
              Bienvenido a MediGest
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Inicia sesión para continuar a tu espacio de trabajo.
            </p>

            <div className="mt-8">
              <AuthActions
                authenticated={false}
                clientId={clientId}
                keycloakIssuer={keycloakIssuer}
              />
            </div>

            <div className="mt-6 rounded-xl bg-slate-50 p-4">
              <p className="text-xs leading-5 text-slate-600">
                La autenticación y recuperación de acceso se gestionan de forma
                segura por tu proveedor institucional.
              </p>
              <p className="mt-3 text-xs font-semibold text-teal-800">
                ¿Necesitas recuperar tu acceso? Usa «¿Olvidaste tu contraseña?» en
                la pantalla de inicio de sesión.
              </p>
            </div>
            <p className="mt-6 text-center text-xs text-slate-500">
              Al continuar, serás redirigido a la página segura de inicio de
              sesión.
            </p>
          </section>
        </div>

        <footer className="flex flex-col gap-2 border-t border-slate-200/80 pt-5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <span>MediGest · Plataforma de gestión de atención médica</span>
          <span>El acceso a la información depende de tus permisos.</span>
        </footer>
      </div>
    </main>
  );
}
