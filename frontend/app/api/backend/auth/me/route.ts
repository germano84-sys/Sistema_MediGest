import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

import { getAuthOptions } from "../../../../../lib/auth";

export async function GET(request: NextRequest) {
  const token = await getToken({
    req: request,
    secret: getAuthOptions().secret,
  });
  const accessToken = token?.accessToken;
  if (typeof accessToken !== "string" || !accessToken) {
    return NextResponse.json(
      { detail: "An active sign-in is required" },
      { status: 401 },
    );
  }

  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    throw new Error("BACKEND_URL is required");
  }

  const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
  const tenantId = request.nextUrl.searchParams.get("tenant_id");
  if (tenantId) {
    headers.set("X-Tenant-ID", tenantId);
  }
  const siteId = request.nextUrl.searchParams.get("site_id");
  if (siteId) {
    headers.set("X-Site-ID", siteId);
  }

  try {
    const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
      headers,
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), {
      status: response.status,
    });
  } catch (error) {
    console.error("Identity profile backend request failed", error);
    return NextResponse.json(
      { detail: "Identity service is unavailable" },
      { status: 503 },
    );
  }
}
