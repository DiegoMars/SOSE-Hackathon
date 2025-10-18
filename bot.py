# bot.py

import os
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load the token from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True   # <-- add this line
bot = commands.Bot(command_prefix="!", intents=intents)

# Simple in-memory scores: {user_id: {"correct": int, "total": int}}
SCORES = {}

def record_result(user_id: int, correct: bool):
    s = SCORES.setdefault(user_id, {"correct": 0, "total": 0})
    s["total"] += 1
    if correct:
        s["correct"] += 1

# A few starter quiz questions
QUESTIONS = [
    {
        "prompt": "What data structure works on a LIFO principle?",
        "choices": ["Queue", "Stack", "Linked List", "Tree"],
        "answer": 1,
        "explanation": "Stack = Last In, First Out."
    },
    {
        "prompt": "Which data structure is best for BFS traversal?",
        "choices": ["Stack", "Queue", "Heap", "Graph"],
        "answer": 1,
        "explanation": "Breadth-first search uses a queue."
    },
    {
        "prompt": "What is the average time complexity for hash table lookups?",
        "choices": ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
        "answer": 0,
        "explanation": "Hash tables give O(1) average lookups if hashing is good."
    },
]

# View class for interactive buttons
class QuizView(discord.ui.View):
    def __init__(self, question, author_id):
        super().__init__(timeout=30)
        self.question = question
        self.author_id = author_id

        # Shuffle the choices
        choices = list(enumerate(question["choices"]))
        random.shuffle(choices)
        self.shuffled = choices
        self.correct_idx = next(i for i,(orig_i,_) in enumerate(choices) if orig_i == question["answer"])

        for i, (_, label) in enumerate(self.shuffled):
            self.add_item(AnswerButton(i, label, self))

class AnswerButton(discord.ui.Button):
    def __init__(self, idx, label, parent_view: QuizView):
        super().__init__(style=discord.ButtonStyle.primary, label=label)
        self.idx = idx
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author_id:
            return await interaction.response.send_message(
                "This question isn’t for you 🙂. Run `!quiz` to play!", ephemeral=True
            )

        correct = (self.idx == self.parent_view.correct_idx)

        for child in self.parent_view.children:
            child.disabled = True

        q = self.parent_view.question
        if correct:
            record_result(interaction.user.id, True)
            text = f"✅ Correct!\n\n**Explanation:** {q['explanation']}"
        else:
            record_result(interaction.user.id, False)
            answer_text = self.parent_view.shuffled[self.parent_view.correct_idx][1]
            text = f"❌ Incorrect. The correct answer was **{answer_text}**.\n\n**Explanation:** {q['explanation']}"

        await interaction.response.edit_message(content=text, view=self.parent_view)

# Commands
@bot.command(name="quiz")
async def quiz(ctx: commands.Context):
    q = random.choice(QUESTIONS)
    embed = discord.Embed(title="Data Structures Quiz", description=q["prompt"])
    view = QuizView(q, ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command(name="score")
async def score(ctx: commands.Context):
    s = SCORES.get(ctx.author.id, {"correct":0, "total":0})
    await ctx.send(f"Your score: **{s['correct']} / {s['total']}**")

# Run the bot
bot.run(TOKEN)
