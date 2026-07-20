# keyboards/inline.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard(theme: str = "Emoji") -> InlineKeyboardMarkup:
    is_emoji = (theme == "Emoji")

    p_add = "➕ New Project" if is_emoji else "[+] New Project"
    p_list = "📚 Projects" if is_emoji else "[P] Projects"
    p_log = "✅ Log Progress" if is_emoji else "[V] Log Progress"
    p_stats = "📊 Statistics" if is_emoji else "[S] Stats"
    p_settings = "⚙️ Settings" if is_emoji else "[*] Settings"
    p_help = "❓ Help" if is_emoji else "[?] Help"

    keyboard = [
        [InlineKeyboardButton(p_add, callback_data="menu_new_project"),
         InlineKeyboardButton(p_list, callback_data="menu_list_projects")],
        [InlineKeyboardButton(p_log, callback_data="menu_log_progress"),
         InlineKeyboardButton(p_stats, callback_data="menu_stats")],
        [InlineKeyboardButton(p_settings, callback_data="menu_settings"),
         InlineKeyboardButton(p_help, callback_data="menu_help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_project_list_keyboard(projects, show_archived_button: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    for p in projects:
        keyboard.append([InlineKeyboardButton(f"{p.name} ({p.status})", callback_data=f"view_project_{p.id}")])
    
    if show_archived_button:
        keyboard.append([InlineKeyboardButton("🗄️ View Archived Projects", callback_data="menu_archived_projects")])

    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_project_detail_keyboard(project_id: int, status: str) -> InlineKeyboardMarkup:
    actions = []
    if status == "Active":
        actions.append(InlineKeyboardButton("⏸️ Pause", callback_data=f"proj_pause_{project_id}"))
    elif status == "Paused":
        actions.append(InlineKeyboardButton("▶️ Resume", callback_data=f"proj_resume_{project_id}"))
    elif status == "Archived":
        # Restore simply sets the project status back to 'Active'
        actions.append(InlineKeyboardButton("▶️ Restore Project", callback_data=f"proj_resume_{project_id}"))

    if status != "Archived":
        actions.append(InlineKeyboardButton("🗄️ Archive", callback_data=f"proj_archive_{project_id}"))

    keyboard = [
        actions,
        [InlineKeyboardButton("✏️ Edit Deadline", callback_data=f"proj_editdl_{project_id}"),
         InlineKeyboardButton("🗑️ Delete", callback_data=f"proj_delete_{project_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="menu_list_projects")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_project_type_keyboard() -> InlineKeyboardMarkup:
    options = ["Book", "PDF", "Slides", "Notes", "Videos"]
    row = [InlineKeyboardButton(o, callback_data=f"ptype_{o}") for o in options]
    return InlineKeyboardMarkup([row[:3], row[3:]])


def get_importance_keyboard() -> InlineKeyboardMarkup:
    options = ["Low", "Medium", "High"]
    row = [InlineKeyboardButton(o, callback_data=f"pimportance_{o}") for o in options]
    return InlineKeyboardMarkup([row])


def get_difficulty_keyboard() -> InlineKeyboardMarkup:
    options = ["Easy", "Medium", "Hard"]
    row = [InlineKeyboardButton(o, callback_data=f"pdifficulty_{o}") for o in options]
    return InlineKeyboardMarkup([row])


def get_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⏰ Wake/Sleep Time", callback_data="set_sleep_wake"),
         InlineKeyboardButton("🌐 Timezone", callback_data="set_timezone")],
        [InlineKeyboardButton("📊 Frequency & Style", callback_data="set_frequency")],
        [InlineKeyboardButton("🎨 Theme Change", callback_data="set_theme")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)