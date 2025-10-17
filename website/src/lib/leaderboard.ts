export type PublicLeaderboardRow = {
  user_id: string;
  total_score: number;
  correct_count: number;
  username: string | null;
  avatar_url: string | null;
};

export async function fetchPublicLeaderboard(limit = 10): Promise<PublicLeaderboardRow[]> {
  const base = import.meta.env.PUBLIC_FUNCTIONS_URL;
  if (!base) throw new Error('PUBLIC_FUNCTIONS_URL is missing');

  const url = `${base}/public-leaderboard?limit=${limit}`;
  // (optional) debug:
  console.log('Fetching leaderboard from:', url);

  const res = await fetch(url, { method: 'GET' });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`Failed to load leaderboard (${res.status}) ${txt ? '- ' + txt : ''}`);
  }
  return res.json();
}
