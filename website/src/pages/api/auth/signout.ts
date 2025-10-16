// Checkout here for more info: https:
// docs.astro.build/en/guides/backend/supabase/#creating-auth-server-endpoints

import type { APIRoute } from "astro";

export const GET: APIRoute = async ({ cookies, redirect }) => {
  cookies.delete("sb-access-token", { path: "/" });
  cookies.delete("sb-refresh-token", { path: "/" });
  return redirect("/signin");
};
