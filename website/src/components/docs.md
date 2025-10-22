---
---
# Data n’structor — Test Commands

Use this document while testing the **Data n’structor** Discord bot.

---

## Setup

Make sure your `.env` file has:

```bash
DISCORD_BOT_TOKEN=your_discord_token_here
DISCORD_GUILD_ID=your_server_id
DISCORD_CLIENT_ID=your_client_id
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
FUNCTIONS_URL=https://<project-ref>.functions.supabase.co
```

Run the bot locally:

```bash
npm run dev
# or
node index.js
```

---

## Commands to Test

### `/challenge`

Posts the current day’s question in the test channel.

### `/answer <your_answer>`

Submits an answer directly from Discord.
Example:

```
/answer O(log n)
```

### `/leaderboard`

Displays the top scorers from Supabase.
Optional:

```
/leaderboard limit:5
```

### `/myrank`

Shows your current rank, score, and streaks.

### `/nextpoll`

Shows the next topic poll or lets users vote via emoji reactions.

### `/ping`

Simple latency check.
Expected response:

```
Ping Bot latency: <x> ms
```

---

## Notes

* Check the console for any API or permission errors.
* If the bot doesn’t respond:

  * Confirm it’s online (`/ping` should work).
  * Make sure slash commands are registered (restart bot if needed).
  * Verify your **Guild ID** and **Client ID** in `.env`.
* For leaderboard tests, ensure your Supabase Edge Function
  [`public-leaderboard`](https://<project-ref>.functions.supabase.co/public-leaderboard)
  returns data when opened in the browser.

---

**Data n’structor**
*Compete. Learn. Grow.*
