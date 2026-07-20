# messages/templates.py
import random

THEMES = {
    "Emoji": {
        "success": "✅", "warning": "⚠️", "target": "🎯", "streak": "🔥",
        "clock": "⏰", "book": "📚", "settings": "⚙️", "stats": "📊", "star": "⭐",
        "bar_filled": "█", "bar_empty": "░"
    },
    "Minimalist": {
        "success": "[Comp]", "warning": "[Warn]", "target": "[Goal]", "streak": "[Stk]",
        "clock": "[Time]", "book": "[Proj]", "settings": "[Set]", "stats": "[Stat]", "star": "[*]",
        "bar_filled": "#", "bar_empty": "-"
    }
}

MOTIVATIONAL_TEMPLATES = [
    "Future you will thank today's effort.",
    "Consistency beats intensity. Keep going!",
    "Small daily progress compounds into massive success.",
    "Every session built brings you closer to mastery.",
    "You don't need motivation. You need habits.",
    "One block at a time, you're building your future.",
    "Do it now. Suffer now and live the rest of your life as a champion.",
    "Focus is a muscle. Train it.",
    "Do not stop until you are proud.",
    "Action is the foundational key to all success."
]

BEHIND_TEMPLATES = [
    "Today's target increased. The sooner you catch up, the easier tomorrow becomes.",
    "A minor setback is a setup for a major comeback. Let's study now!",
    "Your dreams are waiting on the other side of this challenge. Catch up!",
    "Don't lose momentum. Let's finish today's updated plan."
]

AHEAD_TEMPLATES = [
    "Excellent work! You can even finish early at this pace.",
    "You are absolutely crushing your goals! Keep setting the standard.",
    "You've bought yourself some extra flexibility today. Keep up the clean streak!"
]

QUOTES = [
    "The secret of getting ahead is getting started. - Mark Twain",
    "It always seems impossible until it's done. - Nelson Mandela",
    "Our greatest weakness lies in giving up. - Thomas Edison",
    "Don't watch the clock; do what it does. Keep going. - Sam Levenson"
]


def get_theme_pack(user_theme: str):
    return THEMES.get(user_theme, THEMES["Emoji"])


def make_progress_bar(pct: float, theme: str = "Emoji") -> str:
    """Generates a dynamic progress bar styled based on the theme."""
    icons = get_theme_pack(theme)
    filled_char = icons.get("bar_filled", "█")
    empty_char = icons.get("bar_empty", "░")
    
    pct = max(0.0, min(100.0, pct))
    filled_count = int(round(pct / 10))
    empty_count = 10 - filled_count
    return f"{filled_char * filled_count}{empty_char * empty_count} {pct:.1f}%"


def get_motivational_message(project_name: str, remaining: float, unit: str, pace: str, theme: str) -> str:
    icons = get_theme_pack(theme)
    base = f"{icons['clock']} *Study Coach Prompt* for {project_name}:\n"

    if pace == "Behind Schedule":
        quote = random.choice(BEHIND_TEMPLATES)
    elif pace == "Ahead of Schedule":
        quote = random.choice(AHEAD_TEMPLATES)
    else:
        quote = random.choice(MOTIVATIONAL_TEMPLATES)

    specs = f"Remaining target: *{remaining} {unit}*.\n"
    return f"{base}{specs}\n_\"{quote}\"_"