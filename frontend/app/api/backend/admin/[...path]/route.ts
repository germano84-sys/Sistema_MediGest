import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

import { getAuthOptions } from "../../../../../lib/auth";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyAdminRequest(request: NextRequest, context: RouteContext) {
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
  const target = new URL(
    `/api/v1/admin/${encodedPath}`,
    backendUrl,
  );
  target.search = request.nextUrl.search;

  const headers = new Headers({
    Authorization: `Bearer ${accessToken}`,
  });
  if (path[0] === "tenants" && path[1]) {
    headers.set("X-Tenant-ID", path[1]);
  }

  const body =
    request.method === "GET" || request.method === "DELETE"
      ? undefined
      : await request.text();
  if (body) headers.set("Content-Type", request.headers.get("content-type") ?? "application/json");

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("Administration backend request failed", error);
    return NextResponse.json(
      { detail: "Administration service is unavailable" },
      { status: 503 },
    );
  }
}

export const GET = proxyAdminRequest;
export const POST = proxyAdminRequest;
export const PUT = proxyAdminRequest;
export const PATCH = proxyAdminRequest;
export const DELETE = proxyAdminRequest;
