import { useEffect, useState } from 'react';
import { fetchPublicLeaderboard, type PublicLeaderboardRow } from '../../lib/leaderboard';
import styles from './leaderboard.module.css';

export default function Leaderboard({
  limit = 10,
  refreshMs = 5000,
}: { limit?: number; refreshMs?: number }) {
  const [rows, setRows] = useState<PublicLeaderboardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      const data = await fetchPublicLeaderboard(limit);
      setRows(data);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to load');
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [limit, refreshMs]);

  if (error) return <div className={styles.error}>Error: {error}</div>;
  if (!rows) return <div className={styles.loading}>Loading leaderboard…</div>;
  if (rows.length === 0) return <div className={styles.empty}>No submissions yet.</div>;

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>Leaderboard</h2>
      <ol className={styles.list}>
        {rows.map((r, i) => (
          <li key={r.user_id} className={styles.item}>
            <span className={styles.rank}>{i + 1}.</span>
            <img
              src={r.avatar_url ?? 'https://placehold.co/40x40?text=?'}
              alt=""
              className={styles.avatar}
              width={32}
              height={32}
            />
            <div className={styles.info}>
              <div className={styles.name}>{r.username ?? 'Anonymous'}</div>
              <div className={styles.meta}>{r.correct_count} correct</div>
            </div>
            <div className={styles.score}>{r.total_score}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
