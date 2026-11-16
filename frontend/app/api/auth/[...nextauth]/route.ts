import type { NextRequest } from "next/server";
import NextAuth from "next-auth";

import { getAuthOptions } from "../../../../lib/auth";

async function handler(
  request: NextRequest,
  context: { params: Promise<{ nextauth: string[] }> },
) {
  return NextAuth(request, context, getAuthOptions());
}

export { handler as GET, handler as POST };
