// Checkout here for more info: https:
// docs.astro.build/en/guides/backend/supabase/#creating-auth-server-endpoints

import type { APIRoute } from "astro";
import { supabase } from "../../../lib/supabase";

const SITE_URL = import.meta.env.PUBLIC_SITE_URL ?? "http://localhost:4321";

export const POST: APIRoute = async ({ request, cookies, redirect }) => {
  const formData = await request.formData();
  const provider = formData.get("provider")?.toString();
  const validProviders = ["discord"];

  if (provider && validProviders.includes(provider)) {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "discord",
      options: {
        redirectTo: `${SITE_URL}/api/auth/callback`,
      },
    });
    if (error) return new Response(error.message, { status: 500 });
    return redirect(data.url);
  }

};
