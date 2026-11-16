import type { NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

export function getAuthOptions(): NextAuthOptions {
  const requiredSetting = (name: string, value: string | undefined): string => {
    if (!value) {
      throw new Error(`${name} is required`);
    }
    return value;
  };
  const issuer = requiredSetting("KEYCLOAK_ISSUER", process.env.KEYCLOAK_ISSUER);
  const internalIssuer = requiredSetting(
    "KEYCLOAK_INTERNAL_ISSUER",
    process.env.KEYCLOAK_INTERNAL_ISSUER,
  );
  const clientId = requiredSetting(
    "KEYCLOAK_CLIENT_ID",
    process.env.KEYCLOAK_CLIENT_ID,
  );
  const clientSecret = requiredSetting(
    "KEYCLOAK_CLIENT_SECRET",
    process.env.KEYCLOAK_CLIENT_SECRET,
  );
  const secret = requiredSetting("NEXTAUTH_SECRET", process.env.NEXTAUTH_SECRET);

  async function refreshAccessToken(token: {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
  }) {
    if (!token.refreshToken) {
      return { ...token, accessToken: undefined, error: "RefreshTokenError" };
    }

    const response = await fetch(
      `${internalIssuer}/protocol/openid-connect/token`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: clientId,
          client_secret: clientSecret,
          grant_type: "refresh_token",
          refresh_token: token.refreshToken,
        }),
        cache: "no-store",
      },
    );
    if (!response.ok) {
      return { ...token, accessToken: undefined, error: "RefreshTokenError" };
    }

    const refreshed = (await response.json()) as {
      access_token: string;
      expires_in: number;
      refresh_token?: string;
    };
    return {
      ...token,
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + refreshed.expires_in,
      error: undefined,
    };
  }

  return {
    providers: [
      KeycloakProvider({
        clientId,
        clientSecret,
        issuer,
        wellKnown: `${internalIssuer}/.well-known/openid-configuration`,
        authorization: {
          params: {
            scope: "openid email profile",
            acr_values: "2",
          },
        },
        checks: ["pkce", "state"],
      }),
    ],
    secret,
    session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
    cookies: {
      sessionToken: {
        name: `${
          process.env.NODE_ENV === "production" ? "__Secure-" : ""
        }next-auth.session-token`,
        options: {
          httpOnly: true,
          sameSite: "lax",
          path: "/",
          secure: process.env.NODE_ENV === "production",
        },
      },
    },
    pages: { signIn: "/" },
    callbacks: {
      async jwt({ token, account }) {
        if (account) {
          token.accessToken = account.access_token;
          token.refreshToken = account.refresh_token;
          token.expiresAt = account.expires_at;
          return token;
        }

        if (
          token.accessToken &&
          token.expiresAt &&
          Date.now() < token.expiresAt * 1000 - 30_000
        ) {
          return token;
        }
        return { ...token, ...(await refreshAccessToken(token)) };
      },
    },
  };
}
