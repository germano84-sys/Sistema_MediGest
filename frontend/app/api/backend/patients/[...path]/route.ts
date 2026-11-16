import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

import { getAuthOptions } from "../../../../../lib/auth";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyPatientRequest(request: NextRequest, context: RouteContext) {
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
  if (!backendUrl) throw new Error("BACKEND_URL is required");

  const { path } = await context.params;
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const target = new URL(`/api/v1/patients/${encodedPath}`, backendUrl);
  target.search = request.nextUrl.search;

  const headers = new Headers({
    Authorization: `Bearer ${accessToken}`,
  });
  const tenantId = request.headers.get("X-Tenant-ID");
  if (tenantId) headers.set("X-Tenant-ID", tenantId);
  const siteId = request.headers.get("X-Site-ID");
  if (siteId) headers.set("X-Site-ID", siteId);

  const body =
    request.method === "GET" || request.method === "DELETE"
      ? undefined
      : await request.arrayBuffer();
  if (body && body.byteLength) {
    headers.set(
      "Content-Type",
      request.headers.get("content-type") ?? "application/json",
    );
  }

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    const responseHeaders = new Headers();
    for (const header of [
      "Content-Type",
      "Content-Disposition",
      "Cache-Control",
      "X-Content-Type-Options",
    ]) {
      const value = response.headers.get(header);
      if (value) responseHeaders.set(header, value);
    }
    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    console.error("Patient backend request failed");
    return NextResponse.json(
      { detail: "Patient service is unavailable" },
      { status: 503 },
    );
  }
}

export const GET = proxyPatientRequest;
export const POST = proxyPatientRequest;
export const PUT = proxyPatientRequest;
export const PATCH = proxyPatientRequest;
