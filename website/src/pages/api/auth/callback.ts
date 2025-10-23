import type { APIRoute } from "astro";
import { supabase } from "../../../lib/supabase";

export const GET: APIRoute = async ({ url, cookies, redirect }) => {
  const authCode = url.searchParams.get("code");
  if (!authCode) return new Response("No code provided", { status: 400 });

  const { data, error } = await supabase.auth.exchangeCodeForSession(authCode);
  if (error) return new Response(error.message, { status: 500 });

  const { access_token, refresh_token } = data.session;

  cookies.set("sb-access-token", access_token, { path: "/" });
  cookies.set("sb-refresh-token", refresh_token, { path: "/" });

  await supabase.auth.setSession({ access_token, refresh_token });

  const { data: userData, error: userErr } = await supabase.auth.getUser();
  if (userErr || !userData.user)
    return new Response("No user", { status: 500 });
  const u = userData.user;

  const meta = (u.user_metadata ?? {}) as any;
  const username = meta.user_name ?? meta.full_name ?? null;
  const avatar_url = meta.avatar_url ?? null;

  const identities = (u as any).identities ?? [];
  const discordIdentity = identities.find((i: any) => i.provider === "discord");
  const discord_id =
    discordIdentity?.provider_id ?? discordIdentity?.identity_data?.sub ?? null;

  await supabase.from("profiles").upsert({
    id: u.id, // PK from Supabase Auth
    username,
    avatar_url,
    discord_id,
  });

  console.log('[callback] full url:', url.toString());
  return redirect("/dashboard");
};
