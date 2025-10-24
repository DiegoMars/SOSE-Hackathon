# bot.py — MCQ-only, Supabase-backed questions, sequential per-user, per-player thread

import os, json
import discord
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client
import logging

logging.basicConfig(level=logging.INFO)

from discord.errors import Forbidden

async def _unarchive_if_needed(channel: discord.abc.Messageable):
    if isinstance(channel, discord.Thread):
        try:
            if getattr(channel, "archived", False):
                await channel.edit(archived=False)
        except Exception:
            pass



# ---------------- Env & intents ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Missing SUPABASE_URL and/or SUPABASE_SERVICE_ROLE (or SUPABASE_ANON_KEY) in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- Leaderboard helpers ----------------
from datetime import datetime, timezone

LEADERBOARD_TABLE = "leaderboard"  # Supabase table name

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _display_name(user: discord.User | discord.Member) -> str:
    return user.display_name or user.global_name or user.name

def submit_final_score(interaction: discord.Interaction, correct: int, total: int):
    """Upsert one row per (guild, user). Stores Discord ID, displays username."""
    gid = str(interaction.guild_id) if interaction.guild_id else "dm"
    uid = str(interaction.user.id)
    uname = _display_name(interaction.user)

    supabase.table(LEADERBOARD_TABLE).upsert({
        "guild_id": gid,
        "user_id": uid,
        "username": uname,      # keeps last-seen display name
        "correct": int(correct),
        "total": int(total),
        "submitted_at": _now_iso(),
    }, on_conflict="guild_id,user_id").execute()


intents = discord.Intents.default()
intents.message_content = True  # also toggle in Developer Portal → Bot → Message Content Intent
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- Scores & Progress (in-memory) ----------------
SCORES: dict[int, dict[str, int]] = {}     # {user_id: {"correct": int, "total": int}}
PROGRESS: dict[int, int] = {}               # {user_id: next question offset (0-based)}
ACTIVE_USERS: set[int] = set()              # prevent multiple sessions per user
TOTAL_COUNT: int | None = None              # cache total mcq count

def record_result(user_id: int, correct: bool):
    s = SCORES.setdefault(user_id, {"correct": 0, "total": 0})
    s["total"] += 1
    if correct:
        s["correct"] += 1

def get_score(user_id: int) -> tuple[int, int]:
    s = SCORES.get(user_id, {"correct": 0, "total": 0})
    return s["correct"], s["total"]

# ---------------- Supabase helpers (sequential) ----------------
# ---------------- Supabase helpers (sequential, schema-aware for your CSV) ----------------

def _normalize_question(row: dict) -> dict:
    """
    Your schema:
      title (str) = question text
      body (str)  = subtitle/extra text (optional)
      options     = JSON array of {id: "A|B|C|D", text: "..."}
      answer_key  = "A" | "B" | "C" | "D"
    We convert to bot's canonical shape:
      prompt, choices[list[str]], answer[int], explanation(str|""), topic(str|"")
    """
    # Question text
    title = row.get("title")
    body  = row.get("body") or ""
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("Missing 'title' for question.")

    prompt = title.strip()
    if body and isinstance(body, str) and body.strip():
        prompt = f"{title.strip()}\n\n{body.strip()}"

    # Options can be a JSON string or already a list
    opts_raw = row.get("options")
    if isinstance(opts_raw, str):
        try:
            options_list = json.loads(opts_raw)
        except Exception:
            raise RuntimeError("Could not parse 'options' JSON string.")
    elif isinstance(opts_raw, list):
        options_list = opts_raw
    else:
        raise RuntimeError("Invalid 'options' field; expected JSON string or list of objects.")

    # Extract labels in A..D order as they appear
    # Each option is like {"id":"A","text":"A programming language"}
    if not all(isinstance(o, dict) and "text" in o for o in options_list):
        raise RuntimeError("Invalid options entries; expected objects with a 'text' key.")

    choices = [o["text"] for o in options_list]

    # Map answer_key ("A"/"B"/"C"/"D") to index by matching the option's id
    answer_key = row.get("answer_key")
    if isinstance(answer_key, str):
        answer_key = answer_key.strip().upper()
    else:
        raise RuntimeError("Missing 'answer_key' (expected 'A'|'B'|'C'|'D').")

    # Find the index of the option whose "id" matches answer_key
    ids = [o.get("id") for o in options_list]
    try:
        answer_index = ids.index(answer_key)
    except ValueError:
        # Fallback: some data might store the answer text instead of the key
        try:
            answer_index = choices.index(answer_key)
        except ValueError:
            raise RuntimeError("answer_key not found in options id/text.")

    if not (0 <= answer_index < len(choices)):
        raise RuntimeError("Computed answer index is out of range.")

    return {
        "prompt": prompt,
        "choices": choices,
        "answer": answer_index,
        "explanation": row.get("explanation") or "",
        "topic": row.get("topic") or "",
    }


async def ensure_total_count() -> int:
    """
    Count MCQs. Prefer kind='mcq' if present; otherwise count all rows.
    """
    global TOTAL_COUNT
    if TOTAL_COUNT is not None:
        return TOTAL_COUNT

    # Try kind='mcq'
    try:
        res = supabase.table("questions").select("id", count="exact").eq("kind", "mcq").execute()
        cnt = res.count or (len(res.data) if res.data else 0)
    except Exception:
        cnt = 0

    if cnt == 0:
        # Fallback: all rows
        res2 = supabase.table("questions").select("id", count="exact").execute()
        cnt = res2.count or (len(res2.data) if res2.data else 0)

    if cnt == 0:
        raise RuntimeError("No rows found in 'questions' table.")

    TOTAL_COUNT = cnt
    return TOTAL_COUNT


def fetch_mcq_by_offset(offset: int) -> dict:
    """
    Fetch exactly one row by offset in a stable order.
    We first try ordering by 'published_at' (ascending), then fall back to 'id'.
    We also try to filter kind='mcq' first; if that returns nothing, we fetch from all rows.
    """
    def _fetch(with_kind: bool, order_by_published: bool):
        q = supabase.table("questions").select("*")
        if with_kind:
            q = q.eq("kind", "mcq")
        if order_by_published:
            # primary order by published_at asc, add id as a tiebreaker if possible
            try:
                q = q.order("published_at", desc=False)
                # Not all clients allow multiple .order; if it errors it will be caught
                q = q.order("id", desc=False)
            except Exception:
                # If 'published_at' doesn't exist in this project, the server will complain when executing.
                pass
        else:
            q = q.order("id", desc=False)

        return q.range(offset, offset).execute()

    data = None
    # 1) kind + published_at
    try:
        res = _fetch(with_kind=True, order_by_published=True)
        data = res.data or []
    except Exception:
        data = []

    # 2) kind + id
    if not data:
        try:
            res = _fetch(with_kind=True, order_by_published=False)
            data = res.data or []
        except Exception:
            data = []

    # 3) all rows + published_at
    if not data:
        try:
            res = _fetch(with_kind=False, order_by_published=True)
            data = res.data or []
        except Exception:
            data = []

    # 4) all rows + id
    if not data:
        res = _fetch(with_kind=False, order_by_published=False)
        data = res.data or []

    if not data:
        raise IndexError("Offset out of bounds or no data returned.")

    return _normalize_question(data[0])
 
def make_embed_for(q: dict) -> discord.Embed:
    """
    Build the quiz embed from a normalized question dict:
    {
      "prompt": str,
      "choices": list[str],
      "answer": int,
      "explanation": str (optional),
      "topic": str (optional)
    }
    """
    desc = q["prompt"] + "\n\n*Click a button below to answer.*"
    embed = discord.Embed(title="Data Structures Quiz", description=desc)
    if q.get("topic"):
        embed.set_footer(text=f"Topic: {q['topic']}")
    return embed


# ---------------- Views ----------------
class QuizView(discord.ui.View):
    """MCQ buttons for a single question; then offers Next Question?"""
    def __init__(self, question: dict, author_id: int, on_end):
        super().__init__(timeout=300)
        self.q = question
        self.author_id = author_id
        self.on_end = on_end

        # Store the correct label before any shuffling
        choices = question["choices"]
        self.correct_label = choices[question["answer"]]

        # Build buttons in the current order (no shuffle, since you're going sequential)
        for idx, label in enumerate(choices):
            self.add_item(AnswerButton(idx, label, self))

        # Optional skip (doesn't change score, advances via NextQuestionView)
        self.add_item(SkipButton(self))

    async def on_timeout(self):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True
        if self.on_end:
            await self.on_end(reason="timeout")

class AnswerButton(discord.ui.Button):
    def __init__(self, idx: int, label: str, parent_view: "QuizView"):
        super().__init__(style=discord.ButtonStyle.primary, label=label)
        self.idx = idx
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author_id:
            return await interaction.response.send_message(
                "This question isn’t for you 🙂. Run `!quiz` to start your own thread.",
                ephemeral=True
            )

        # Disable buttons
        for c in self.parent_view.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True

        q = self.parent_view.q
        correct = (self.idx == q["answer"])
        record_result(interaction.user.id, correct)

        if correct:
            text = f"✅ Correct!\n\n**Explanation:** {q.get('explanation','')}"
        else:
            text = (
                f"❌ Incorrect. The correct answer was **{self.parent_view.correct_label}**.\n\n"
                f"**Explanation:** {q.get('explanation','')}"
            )

        # Edit result; if thread is archived, unarchive then retry once
        try:
            await interaction.response.edit_message(content=text, view=self.parent_view)
        except Forbidden:
            await _unarchive_if_needed(interaction.channel)
            await interaction.response.edit_message(content=text, view=self.parent_view)

        # Follow-up "next question?" message with the same retry protection
        corr, tot = get_score(interaction.user.id)
        prompt = f"Want the next one? (**Your score:** {corr}/{tot})"
        try:
            await interaction.followup.send(prompt, view=NextQuestionView(self.parent_view.author_id, self.parent_view.on_end))
        except Forbidden:
            await _unarchive_if_needed(interaction.channel)
            await interaction.followup.send(prompt, view=NextQuestionView(self.parent_view.author_id, self.parent_view.on_end))

class SkipButton(discord.ui.Button):
    def __init__(self, parent_view: QuizView):
        super().__init__(style=discord.ButtonStyle.secondary, label="Skip ⏭️")
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author_id:
            return await interaction.response.send_message("Not your quiz 🙂", ephemeral=True)

        for c in self.parent_view.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True

        await interaction.response.edit_message(
            content=f"⏭️ Skipped. The correct answer was **{self.parent_view.correct_label}**.",
            view=self.parent_view
        )

        corr, tot = get_score(self.parent_view.author_id)
        await interaction.followup.send(
            f"Want the next one? (**Your score:** {corr}/{tot})",
            view=NextQuestionView(self.parent_view.author_id, self.parent_view.on_end)
        )

class NextQuestionView(discord.ui.View):
    """Prompt to continue with Yes/No."""
    def __init__(self, author_id: int, on_end):
        super().__init__(timeout=300)  # was 30; give users more time
        self.author_id = author_id
        self.on_end = on_end

    async def on_timeout(self):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True
        # Do NOT call on_end() here (which might archive); just let thread live

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This prompt isn’t for you 🙂.", ephemeral=True)

        total = await ensure_total_count()
        offset = PROGRESS.get(self.author_id, 0)
        if offset >= total:
            corr, tot = get_score(self.author_id)
            try:
                await interaction.response.send_message(f"🎉 You’ve reached the end! Final score: **{corr}/{tot}**")
            except Forbidden:
                await _unarchive_if_needed(interaction.channel)
                await interaction.response.send_message(f"🎉 You’ve reached the end! Final score: **{corr}/{tot}**")
            
            # NEW: record to Supabase leaderboard
            submit_final_score(interaction, corr, tot)
            
            if self.on_end:
                await self.on_end(reason="complete")
            return

        # Next question (sequential)
        q = fetch_mcq_by_offset(offset)
        embed = make_embed_for(q)
        try:
            await interaction.response.send_message(embed=embed, view=QuizView(q, self.author_id, self.on_end))
        except Forbidden:
            await _unarchive_if_needed(interaction.channel)
            await interaction.response.send_message(embed=embed, view=QuizView(q, self.author_id, self.on_end))
        PROGRESS[self.author_id] = offset + 1

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This prompt isn’t for you 🙂.", ephemeral=True)
        corr, tot = get_score(self.author_id)
        try:
            await interaction.response.send_message(f"All good! Final score: **{corr}/{tot}**. Thanks for playing!")
        except Forbidden:
            await _unarchive_if_needed(interaction.channel)
            await interaction.response.send_message(f"All good! Final score: **{corr}/{tot}**. Thanks for playing!")
        
        # NEW: record to Supabase leaderboard
        submit_final_score(interaction, corr, tot)
        
        if self.on_end:
            await self.on_end(reason="user-finished")

# ---------------- Thread/session helpers ----------------
async def start_quiz_in_thread(ctx: commands.Context):
    """Create (or reuse) a thread for this user and start the session there, sequentially."""
    thread: discord.abc.Messageable | None = None

    # Reuse current thread if already inside one
    if isinstance(ctx.channel, discord.Thread):
        thread = ctx.channel

    # Forum channel: must create a post (thread) with initial content
    elif isinstance(ctx.channel, discord.ForumChannel):
        name = f"quiz-{ctx.author.display_name}".replace("/", "-")[:90]
        try:
            created = await ctx.channel.create_thread(
                name=name,
                content=f"{ctx.author.mention} setting up your quiz…",
                auto_archive_duration=1440
            )
            # Some discord.py versions return (thread, first_message)
            if isinstance(created, tuple):
                thread, _first_message = created
            else:
                thread = created
        except discord.Forbidden:
            return await ctx.send("❌ Missing permission: **Create Posts** / **Send Messages in Posts** for forums.")
        except discord.HTTPException as e:
            return await ctx.send(f"❌ Couldn’t create a forum post. ({e})")

    # Regular text channel: create a public thread, then join & send
    elif isinstance(ctx.channel, (discord.TextChannel, discord.VoiceChannel)):
        name = f"quiz-{ctx.author.display_name}".replace("/", "-")[:90]
        try:
            thread = await ctx.channel.create_thread(
                name=name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60
            )
        except discord.Forbidden:
            return await ctx.send("❌ I need **Create Public Threads** and **Send Messages in Threads** here.")
        except discord.HTTPException as e:
            return await ctx.send(f"❌ I couldn’t create a thread here. ({e})")

    else:
        return await ctx.send("❌ I can only start quizzes in Text or Forum channels.")

    # Ensure bot is a member of the thread before sending
    try:
        await thread.join()
    except Exception:
        pass  # fine if already joined

    # Quick speak test inside the thread (for non-forum threads)
    try:
        if not isinstance(ctx.channel, discord.ForumChannel):
            await thread.send(f"{ctx.author.mention} setting up your quiz…")
    except discord.Forbidden:
        return await ctx.send("❌ I can’t post in the thread. Please allow **Send Messages in Threads**.")
    except discord.HTTPException as e:
        return await ctx.send(f"❌ I couldn’t post in the thread. ({e})")

    # Session bookkeeping + cleanup helper
    ACTIVE_USERS.add(ctx.author.id)

    async def end_session(reason: str):
        ACTIVE_USERS.discard(ctx.author.id)
        try:
            if isinstance(thread, discord.Thread) and not thread.locked:
                await thread.send(f"(Session ended: {reason}. This thread will auto-archive soon.)")
                # Optional immediate archive; remove this next line if you prefer auto-archive only:
                await thread.edit(archived=True, locked=False)
        except Exception:
            logging.exception("Thread cleanup failed")

    # Initialize progress
    if ctx.author.id not in PROGRESS:
        PROGRESS[ctx.author.id] = 0

    # Fetch first (or next) question sequentially
    try:
        total = await ensure_total_count()
        offset = PROGRESS.get(ctx.author.id, 0)
        if offset >= total:
            return await thread.send(
                f"{ctx.author.mention} You’ve finished all questions! Use `!score` or ask a mod to run `!resetprogress`."
            )

        q = fetch_mcq_by_offset(offset)
        embed = make_embed_for(q)
        await thread.send(content="🎯 First question:" if offset == 0 else "➡️ Next question:", embed=embed, view=QuizView(q, ctx.author.id, end_session))
        PROGRESS[ctx.author.id] = offset + 1

    except Exception as e:
        await thread.send(f"❌ Error starting quiz: `{e}`")
        logging.exception("Error while starting quiz")
        await end_session("error")


# ---------------- Commands ----------------
@bot.command(name="quiz")
async def quiz(ctx: commands.Context):
    if ctx.author.id in ACTIVE_USERS:
        return await ctx.send(f"{ctx.author.mention} you already have a running quiz. Finish it or wait for it to time out.")
    await start_quiz_in_thread(ctx)

@bot.command(name="score")
async def score(ctx: commands.Context):
    corr, tot = get_score(ctx.author.id)
    await ctx.send(f"{ctx.author.mention} Your score: **{corr} / {tot}**")

@bot.command(name="resetprogress")
@commands.has_permissions(manage_messages=True)
async def resetprogress(ctx: commands.Context, member: discord.Member | None = None):
    """Admin/mod command: reset your or someone else's question pointer to 0."""
    target = member or ctx.author
    PROGRESS[target.id] = 0
    await ctx.send(f"🔁 Progress reset for {target.mention}. Next question will be the first one.")

# ---------------- Run ----------------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN in .env")
    bot.run(TOKEN)
