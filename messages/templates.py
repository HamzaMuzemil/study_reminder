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

ENGLISH_QUOTES = [
    "The secret of getting ahead is getting started. - Mark Twain",
    "It always seems impossible until it's done. - Nelson Mandela",
    "Our greatest weakness lies in giving up. - Thomas Edison",
    "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
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

AMHARIC_QUOTES = [
    "ካላነበቡ አይታወቁ፣ ካልዘሩ አይታጨዱ።",
    "ቀስ በቀስ፣ እንቁላል በእግሩ ይሄዳል",
    "የተማረ ያውቃል፣ ያረሰ ይበላል",
    "ከመጽሐፍ የወጣ እውቀት፣ ከወርቅ የጠራ ሀብት ነው",
    "ያነበበ ይበልጣል፣ የጠየቀ ይረዳል፤ የማይደክም ያሸንፋል",
    "ዛሬ ያነበበ፣ ነገ ይመራል",
    "የዕውቀት መጀመሪያ ማንበብ፣ የመጨረሻው ጥበብ ነው",
    "ሰው በምግብ ብቻ አይኖርም፣ አእምሮም በንባብ ያድጋል",
    "ውኃ ቢወርዱበት አያልቅም፣ መጽሐፍ ቢያነቡት አይሰለችም",
    "ያልደከሙበት እውቀት፣ ያልዘሩት እህል ነው",
    "የጨለማ መብራት መጽሐፍ፣ የድንቁርና መድኃኒት እውቀት ነው",
    "በትእግሥት ያነበበ፣ በመጨረሻ ይደሰታል",
    "የዛሬ ድካም፣ የነገ ብርሃን ነው",
    "እውቀት ከሀብት ይበልጣል፣ ማንበብ ከምንም ይልቃል",
    "የተከፈተ መጽሐፍ፣ ክፍት አእምሮን ይፈጥራል",
    "ሳይማሩ ማወቅ፣ ሳይዘሩ ማጨድ የለም",
    "አንድ ገጽ ማንበብ፣ ወደ ስኬት አንድ እርምጃ መራመድ ነው",
    "የጽናት ፍሬ ሁልጊዜ ጣፋጭ ነው",
    "ዛሬ የተከልከው የንባብ ዘር፣ ነገ ትልቅ ጥላ ይሆናል"
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


def get_alternating_quote(total_runs: int) -> str:
    """
    Returns an alternating English/Amharic quote based on user total runs
    without repeating consecutive quotes.
    """
    if total_runs % 2 == 0:
        idx = (total_runs // 2) % len(ENGLISH_QUOTES)
        return ENGLISH_QUOTES[idx]
    else:
        idx = (total_runs // 2) % len(AMHARIC_QUOTES)
        return AMHARIC_QUOTES[idx]


def get_motivational_message(project_name: str, remaining: float, unit: str, pace: str, theme: str, quote: str) -> str:
    icons = get_theme_pack(theme)
    base = f"{icons['clock']} *Study Coach Prompt* for {project_name}:\n"
    specs = f"Remaining target: *{remaining} {unit}*.\n"
    return f"{base}{specs}\n_\"{quote}\"_"