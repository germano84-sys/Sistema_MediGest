import { getServerSession } from "next-auth";

import { AuthenticatedWorkspace } from "../components/authenticated-workspace";
import { LoginView } from "../components/login-view";
import { getAuthOptions } from "../lib/auth";

export const dynamic = "force-dynamic";

export default async function Home() {
  const session = await getServerSession(getAuthOptions());

  if (!session?.user) {
    return (
      <LoginView
        clientId={process.env.KEYCLOAK_CLIENT_ID ?? ""}
        keycloakIssuer={process.env.KEYCLOAK_ISSUER ?? ""}
      />
    );
  }

  return (
    <AuthenticatedWorkspace
      clientId={process.env.KEYCLOAK_CLIENT_ID ?? ""}
      keycloakIssuer={process.env.KEYCLOAK_ISSUER ?? ""}
      user={{
        name: session.user.name ?? null,
        email: session.user.email ?? null,
      }}
    />
  );
}
