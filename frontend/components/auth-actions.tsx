"use client";

import { signIn, signOut } from "next-auth/react";
import { ArrowRight, LogOut } from "lucide-react";

type AuthActionsProps = {
  authenticated: boolean;
  keycloakIssuer: string;
  clientId: string;
};

export function AuthActions({
  authenticated,
  keycloakIssuer,
  clientId,
}: AuthActionsProps) {
  if (authenticated) {
    return (
      <button
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        onClick={async () => {
          const result = await signOut({ redirect: false, callbackUrl: "/" });
          const logoutUrl = new URL(
            `${keycloakIssuer}/protocol/openid-connect/logout`,
          );
          logoutUrl.searchParams.set("client_id", clientId);
          logoutUrl.searchParams.set(
            "post_logout_redirect_uri",
            new URL(result.url, window.location.origin).toString(),
          );
          window.location.assign(logoutUrl.toString());
        }}
        type="button"
      >
        <LogOut aria-hidden="true" size={16} />
        Cerrar sesión
      </button>
    );
  }

  return (
    <button
      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
      onClick={() => signIn("keycloak")}
      type="button"
    >
      Acceder a MediGest
      <ArrowRight aria-hidden="true" size={17} />
    </button>
  );
}
