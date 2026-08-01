# handlers/project.py
import logging
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database import AsyncSessionLocal
from sqlalchemy import select
from models import Project, User
from services.coach_logic import calculate_metrics, get_user_local_today
from keyboards.inline import (
    get_project_list_keyboard,
    get_project_detail_keyboard,
    get_main_menu_keyboard,
    get_project_type_keyboard,
    get_importance_keyboard,
    get_difficulty_keyboard,
)
from messages.templates import get_theme_pack, make_progress_bar
from handlers.common import cancel, menu_callback_fallback

logger = logging.getLogger(__name__)

(
    PROJ_NAME, PROJ_COURSE, PROJ_TYPE, PROJ_UNIT,
    PROJ_TOTAL, PROJ_COMPLETED, PROJ_DEADLINE,
    PROJ_HOURS, PROJ_IMPORTANCE, PROJ_DIFFICULTY, PROJ_NOTES
) = range(11)

# Separate state for the standalone "edit deadline" wizard below.
EDIT_DEADLINE = 100


# --- Dynamic Onboarding Keyboards ---

def get_cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel & Quit", callback_data="menu_main")]])


def get_skip_cancel_keyboard(skip_callback: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Skip", callback_data=skip_callback)],
        [InlineKeyboardButton("❌ Cancel & Quit", callback_data="menu_main")]
    ])


# --- Sequential Setup Steps ---

async def start_add_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 *Step 1 of 11: Project Title*\n\n"
        "What is the name of this study project?\n\n"
        "_Examples: 'Robbins Pathology', 'Organic Chemistry III', 'AWS Practitioner'_",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_NAME


async def add_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["p_name"] = update.message.text
    await update.message.reply_text(
        "📚 *Step 2 of 11: Course / Book affiliation*\n\n"
        "What course or textbook is this affiliated with?\n\n"
        "_Tap 'Skip' or type the subject name below:_",
        parse_mode="Markdown",
        reply_markup=get_skip_cancel_keyboard("proj_skip_course")
    )
    return PROJ_COURSE


async def add_project_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["p_course"] = update.message.text
    return await transition_to_type(update, context)


async def add_project_course_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["p_course"] = None
    return await transition_to_type(update, context, edit=True)


async def transition_to_type(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False) -> int:
    # Retrieve base type keyboard and attach Cancel button to the bottom row
    orig_markup = get_project_type_keyboard()
    keyboard = list(orig_markup.inline_keyboard)
    keyboard.append([InlineKeyboardButton("❌ Cancel & Quit", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🛠️ *Step 3 of 11: Material Format*\n\n"
        "Select the medium format of your study material:"
    )
    
    # Corrected update validation to prevent AttributeError on Message instances
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.effective_chat.send_message(text, parse_mode="Markdown", reply_markup=reply_markup)
            
    return PROJ_TYPE


async def add_project_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chosen_type = query.data.replace("ptype_", "")
    context.user_data["p_type"] = chosen_type

    await query.edit_message_text(
        f"Material Type set to: *{chosen_type}*\n\n"
        "📈 *Step 4 of 11: Progress Metric*\n\n"
        "What unit will you use to track your milestones?\n\n"
        "_Examples: 'Pages', 'Slides', 'Chapters', 'Lessons', 'Hours'_",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_UNIT


async def add_project_unit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["p_unit"] = update.message.text
    unit = context.user_data["p_unit"]
    await update.message.reply_text(
        "🎯 *Step 5 of 11: Total Target*\n\n"
        f"What is the total quantity of *{unit}* to complete?\n\n"
        "_(Please enter a positive whole number, e.g. 350 or 45)_", 
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_TOTAL


async def add_project_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        total = float(update.message.text)
        if total <= 0:
            raise ValueError
        context.user_data["p_total"] = total
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid positive number:",
            reply_markup=get_cancel_keyboard()
        )
        return PROJ_TOTAL

    unit = context.user_data.get("p_unit", "units")
    await update.message.reply_text(
        "🏁 *Step 6 of 11: Prior Progress*\n\n"
        f"How much have you already completed out of the target?\n\n"
        f"_(Enter a number in {unit}. Send 0 if starting fresh)_", 
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_COMPLETED


async def add_project_completed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        completed = float(update.message.text)
        if completed < 0:
            raise ValueError
        if completed > context.user_data["p_total"]:
            await update.message.reply_text(
                "That exceeds the total amount. Please enter a value equal to or lower than the total target:",
                reply_markup=get_cancel_keyboard()
            )
            return PROJ_COMPLETED
        context.user_data["p_completed"] = completed
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid positive number (or 0):",
            reply_markup=get_cancel_keyboard()
        )
        return PROJ_COMPLETED

    await update.message.reply_text(
        "📅 *Step 7 of 11: Target Deadline*\n\n"
        "When do you plan to finish this project?\n\n"
        "_(Please enter a future date in standard YYYY-MM-DD format, e.g. 2026-12-31)_", 
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_DEADLINE


async def add_project_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == update.effective_user.id))
        user = user_res.scalar_one_or_none()
    local_today = get_user_local_today(user) if user else date.today()

    try:
        deadline_date = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").date()
        if deadline_date < local_today:
            await update.message.reply_text(
                "The deadline cannot be in the past. Please enter a future date (YYYY-MM-DD):",
                reply_markup=get_cancel_keyboard()
            )
            return PROJ_DEADLINE
        context.user_data["p_deadline"] = deadline_date
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid date in YYYY-MM-DD format (e.g. 2026-09-01):",
            reply_markup=get_cancel_keyboard()
        )
        return PROJ_DEADLINE

    await update.message.reply_text(
        "⏱️ *Step 8 of 11: Daily Time Allocation*\n\n"
        "How many hours per day do you plan to commit to studying this?\n\n"
        "_(Examples: 1.5, 3.0, 5)_", 
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return PROJ_HOURS


async def add_project_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        hours = float(update.message.text)
        if hours <= 0:
            raise ValueError
        context.user_data["p_hours"] = hours
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid positive number of hours:",
            reply_markup=get_cancel_keyboard()
        )
        return PROJ_HOURS

    # Append Cancel button to the priority configuration buttons
    orig_markup = get_importance_keyboard()
    keyboard = list(orig_markup.inline_keyboard)
    keyboard.append([InlineKeyboardButton("❌ Cancel & Quit", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⭐ *Step 9 of 11: Priority Level*\n\n"
        "Select the overall importance of this project:", 
        reply_markup=reply_markup
    )
    return PROJ_IMPORTANCE


async def add_project_importance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chosen = query.data.replace("pimportance_", "")
    context.user_data["p_importance"] = chosen

    await query.edit_message_text(f"Priority level set to: *{chosen}*", parse_mode="Markdown")
    
    # Append Cancel button to difficulty keyboard
    orig_markup = get_difficulty_keyboard()
    keyboard = list(orig_markup.inline_keyboard)
    keyboard.append([InlineKeyboardButton("❌ Cancel & Quit", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        "🧠 *Step 10 of 11: Subject Difficulty*\n\n"
        "Select the expected difficulty level of this material:", 
        reply_markup=reply_markup
    )
    return PROJ_DIFFICULTY


async def add_project_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chosen = query.data.replace("pdifficulty_", "")
    context.user_data["p_difficulty"] = chosen

    await query.edit_message_text(
        f"Difficulty set to: *{chosen}*\n\n"
        "📝 *Step 11 of 11: Reference Notes*\n\n"
        "Would you like to add any personal remarks or guidelines to this track?\n\n"
        "_Tap 'Skip' or type your notes below:_",
        parse_mode="Markdown",
        reply_markup=get_skip_cancel_keyboard("proj_skip_notes")
    )
    return PROJ_NOTES


async def save_project(user_id, context, notes):
    """Database persistence helper."""
    async with AsyncSessionLocal() as session:
        new_project = Project(
            user_id=user_id,
            name=context.user_data["p_name"],
            course_name=context.user_data["p_course"],
            type=context.user_data["p_type"],
            unit=context.user_data["p_unit"],
            total_amount=context.user_data["p_total"],
            completed_amount=context.user_data["p_completed"],
            deadline=context.user_data["p_deadline"],
            daily_study_hours=context.user_data["p_hours"],
            importance=context.user_data["p_importance"],
            difficulty=context.user_data["p_difficulty"],
            notes=notes,
            status="Active",
        )
        session.add(new_project)
        await session.commit()

    # Clear only onboarding keys from state
    for key in list(context.user_data.keys()):
        if key.startswith("p_"):
            context.user_data.pop(key, None)


async def add_project_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    notes = update.message.text
    user_id = update.effective_user.id
    await save_project(user_id, context, notes)
    
    await update.message.reply_text(
        "🎉 *Project Created Successfully!*\n\n"
        "Your study schedule and notifications have been initialized. "
        "You can now view this tracker on your dashboard.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


async def add_project_notes_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await save_project(user_id, context, None)
    
    await query.edit_message_text(
        "🎉 *Project Created Successfully!*\n\n"
        "Your study schedule and notifications have been initialized. "
        "You can now view this tracker on your dashboard.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# --- List and detail views ---

async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(
            select(Project).where(Project.user_id == query.from_user.id, Project.status != "Archived")
        )
        projects = proj_res.scalars().all()

        archived_res = await session.execute(
            select(Project).where(Project.user_id == query.from_user.id, Project.status == "Archived")
        )
        has_archived = len(archived_res.scalars().all()) > 0

    if not projects and not has_archived:
        await query.edit_message_text(
            "📭 You don't have any projects yet. Use *➕ New Project* on the dashboard to get started.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await query.edit_message_text(
        "📚 *Your Projects*\n\nTap one to see details or make changes:",
        parse_mode="Markdown",
        reply_markup=get_project_list_keyboard(projects, show_archived_button=has_archived),
    )


async def list_archived_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(
            select(Project).where(Project.user_id == query.from_user.id, Project.status == "Archived")
        )
        projects = proj_res.scalars().all()

    if not projects:
        await query.edit_message_text(
            "📭 You do not have any archived projects.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await query.edit_message_text(
        "🗄️ *Archived Projects*\n\nTap one to view details or restore:",
        parse_mode="Markdown",
        reply_markup=get_project_list_keyboard(projects, show_archived_button=False),
    )


async def view_project_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    project_id = int(query.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()

        user_res = await session.execute(select(User).where(User.id == query.from_user.id))
        user = user_res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"

    if not p or p.user_id != query.from_user.id:
        await query.edit_message_text("That project couldn't be found.")
        return

    icons = get_theme_pack(theme)
    local_today = get_user_local_today(user) if user else date.today()
    metrics = calculate_metrics(p, today=local_today)
    
    progress_bar_str = make_progress_bar(metrics['completion_pct'], theme)

    detail_txt = (
        f"{icons['book']} *{p.name}* ({p.status})\n"
        f"📖 Course: {p.course_name or 'N/A'}\n"
        f"🛠️ Type: {p.type} | Importance: {p.importance} | Difficulty: {p.difficulty}\n\n"
        f"🎯 *Progress*:\n"
        f"- Progress bar: {progress_bar_str}\n"
        f"- Completed: {p.completed_amount}/{p.total_amount} {p.unit} ({metrics['completion_pct']}%)\n"
        f"- Remaining: {metrics['remaining_material']} {p.unit}\n"
        f"- Days left: {metrics['days_remaining']}\n"
        f"- Daily target: *{metrics['daily_target']} {p.unit}/day*\n"
        f"- Weekly pace: {metrics['weekly_target']} {p.unit}/week\n"
        f"- Status: *{metrics['pace_status']}*\n"
        f"- Estimated finish: {metrics['estimated_completion']}\n\n"
        f"📝 _Notes: {p.notes or 'None'}_"
    )

    await query.edit_message_text(
        text=detail_txt,
        parse_mode="Markdown",
        reply_markup=get_project_detail_keyboard(p.id, p.status),
    )


async def handle_project_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    action = parts[1]
    project_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()

        if not p or p.user_id != query.from_user.id:
            await query.edit_message_text("That project couldn't be found.")
            return

        if action == "pause":
            p.status = "Paused"
            msg = f"⏸️ '{p.name}' paused."
        elif action == "resume":
            p.status = "Active"
            msg = f"▶️ '{p.name}' is active again."
        elif action == "archive":
            p.status = "Archived"
            msg = f"🗄️ '{p.name}' archived."
        elif action == "delete":
            proj_name = p.name
            await session.delete(p)
            await session.commit()
            await query.edit_message_text(
                f"🗑️ '{proj_name}' deleted.", reply_markup=get_main_menu_keyboard()
            )
            return
        else:
            await query.edit_message_text("Unknown action.")
            return

        await session.commit()
        await query.edit_message_text(f"{msg}\n\nUse the menu below to continue:", reply_markup=get_main_menu_keyboard())


# --- Edit deadline mini-wizard ---

async def start_edit_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    project_id = int(query.data.split("_")[-1])
    context.user_data["edit_deadline_project_id"] = project_id

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()

    if not p or p.user_id != query.from_user.id:
        await query.edit_message_text("That project couldn't be found.")
        return ConversationHandler.END

    await query.edit_message_text(
        f"✏️ *Edit Deadline for {p.name}*\n\n"
        f"Current deadline: {p.deadline.isoformat()}\n\n"
        "Send the new deadline (Format: YYYY-MM-DD):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return EDIT_DEADLINE


async def save_edit_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    project_id = context.user_data.get("edit_deadline_project_id")
    if project_id is None:
        await update.message.reply_text("That session expired. Please reopen the project and try again.")
        return ConversationHandler.END

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == update.effective_user.id))
        user = user_res.scalar_one_or_none()
    local_today = get_user_local_today(user) if user else date.today()

    try:
        new_deadline = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").date()
        if new_deadline < local_today:
            await update.message.reply_text(
                "The deadline can't be in the past. Please enter a future date (YYYY-MM-DD):",
                reply_markup=get_cancel_keyboard()
            )
            return EDIT_DEADLINE
    except ValueError:
        await update.message.reply_text(
            "That doesn't match YYYY-MM-DD. Please try again:",
            reply_markup=get_cancel_keyboard()
        )
        return EDIT_DEADLINE

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()
        if not p or p.user_id != update.effective_user.id:
            await update.message.reply_text("That project couldn't be found.")
            return ConversationHandler.END
        p.deadline = new_deadline
        await session.commit()
        proj_name = p.name

    await update.message.reply_text(
        f"✅ Deadline for *{proj_name}* updated to {new_deadline.isoformat()}. "
        "Daily/weekly targets will recalculate automatically.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )
    return ConversationHandler.END


add_project_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_project, pattern="^menu_new_project$")],
    states={
        PROJ_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_name)],
        PROJ_COURSE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_course),
            CallbackQueryHandler(add_project_course_skip, pattern="^proj_skip_course$")
        ],
        PROJ_TYPE: [CallbackQueryHandler(add_project_type, pattern="^ptype_")],
        PROJ_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_unit)],
        PROJ_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_total)],
        PROJ_COMPLETED: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_completed)],
        PROJ_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_deadline)],
        PROJ_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_hours)],
        PROJ_IMPORTANCE: [CallbackQueryHandler(add_project_importance, pattern="^pimportance_")],
        PROJ_DIFFICULTY: [CallbackQueryHandler(add_project_difficulty, pattern="^pdifficulty_")],
        PROJ_NOTES: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_notes),
            CallbackQueryHandler(add_project_notes_skip, pattern="^proj_skip_notes$")
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CallbackQueryHandler(menu_callback_fallback, pattern="^menu_")
    ],
    per_message=False
)

edit_deadline_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_deadline, pattern=r"^proj_editdl_\d+$")],
    states={
        EDIT_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_deadline)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CallbackQueryHandler(menu_callback_fallback, pattern="^menu_")
    ],
    per_message=False
)