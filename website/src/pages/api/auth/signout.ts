// Checkout here for more info: https:
// docs.astro.build/en/guides/backend/supabase/#creating-auth-server-endpoints

import type { APIRoute } from "astro";
import { supabase } from "../../../lib/supabase";

const SITE_URL = import.meta.env.PUBLIC_SITE_URL ?? "http://localhost:4321";

export const GET: APIRoute = async ({ cookies, redirect }) => {
  await supabase.auth.signOut().catch(() => {});
  cookies.delete("sb-access-token", { path: "/" });
  cookies.delete("sb-refresh-token", { path: "/" });
  return redirect("/");
};

// export const GET: APIRoute = async (ctx) => {
//   // Optional: support GET /api/auth/signout so you can use a simple link
//   return await POST(ctx as any);
// };
