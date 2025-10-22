# SOSE Hackathon — Data n' Structor Quiz Bot 🧠

An interactive **Discord bot** that quizzes users on **Data Structures and Algorithms** concepts.

---

## 🚀 Features
- 🧩 Multiple-choice questions (pulled from Supabase)
- 💬 Interactive Discord buttons
- 🧠 Tracks user scores and updates a Supabase leaderboard
- 🧑‍💻 Beginner-friendly, fully commented Python code
- ☁️ Easy to deploy (locally or on Railway)
- 🔄 Sequential question flow (one question per thread per user)
- 🏆 Leaderboard stored in Supabase — shows usernames, not IDs

---

## 🧰 Tech Stack
- **Python 3.10+**
- **discord.py** (Discord API wrapper)
- **Supabase** (PostgreSQL + REST API)
- **python-dotenv** (environment config)

---

## ⚙️ Setup Instructions

### Step 1: Clone the Repository
git clone https://github.com/DiegoMars/SOSE-Hackathon.git
cd SOSE-Hackathon/ds-quiz-bot

### Step 2: Create a Virtual Environment
python -m venv .venv
# Activate it:
# Windows Git Bash:
source .venv/Scripts/activate
# PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

### Step 3: Install dependencies
pip install -r requirements.txt

### Step 4: Configure Environment Variables
cp .env.example .env

### Then fill it out:
    
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE=YOUR_SUPABASE_SERVICE_ROLE_KEY

### Step 5: Create the Leaderboard Table in Supabase
### Run this SQL in Supabase → SQL Editor:
    
create table if not exists public.leaderboard (
  id           bigserial primary key,
  guild_id     text,
  user_id      text not null,
  username     text not null,
  correct      int4  not null,
  total        int4  not null,
  submitted_at timestamptz not null default now(),
  unique (guild_id, user_id)
);

create index if not exists leaderboard_rank
  on public.leaderboard (guild_id, correct desc, total asc, submitted_at desc);

alter table public.leaderboard disable row level security;

### (If you have a “questions” table already from earlier setup, you’re good — that’s where the bot pulls questions.)

### Step 6: Run the Bot

py bot.py

### You should see:

INFO:discord.client:logging in using static token
INFO:discord.gateway:Connected to gateway.


### Discord Bot Setup (if you’re new)
1. Go to the Discord Developer Portal
2. 