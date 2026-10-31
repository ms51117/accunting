import os
import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any, List
import httpx
import jdatetime
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.cheque import Cheque, ChequeStatus, ChequeType
from app.models.user import User
from app.utils.jalali import format_rial, to_jalali_str

logger = logging.getLogger("telegram_service")


async def send_telegram_message(chat_id: str, message: str) -> bool:
    """ارسال پیام متنی با فرمت HTML به شناسه تلگرام مشخص"""
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not bot_token or not chat_id:
        logger.warning("Bot token or chat_id is missing.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    proxy = (
        getattr(settings, "HTTPS_PROXY", None)
        or getattr(settings, "HTTP_PROXY", None)
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
    )
    client_kwargs = {"timeout": 8.0}
    if proxy:
        client_kwargs["proxy"] = proxy

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                logger.info(f"Telegram reminder successfully sent to {chat_id}")
                return True
            logger.error(f"Telegram API Error ({res.status_code}): {res.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")
        return False


def build_cheque_notification_message(
    user: User,
    today: date,
    today_cheques: List[Cheque],
    tomorrow_cheques: List[Cheque],
    upcoming_cheques: List[Cheque],
    overdue_cheques: List[Cheque]
) -> str:
    """ساخت متن گزارش و هشدار سررسید چک‌ها با فونت‌دهی ایموجی و استایل حرفه‌ای فارسی"""
    today_jd = jdatetime.date.fromgregorian(date=today)
    shamsi_today_str = f"{today_jd.strftime('%A %d %B %Y')}"

    total_payable = 0
    total_receivable = 0

    all_cheques = today_cheques + tomorrow_cheques + upcoming_cheques + overdue_cheques
    for c in all_cheques:
        if c.type == "PAYABLE" or c.type == ChequeType.PAYABLE:
            total_payable += (c.amount or 0)
        else:
            total_receivable += (c.amount or 0)

    lines = []
    lines.append("🔔 <b>یادآور سررسید چک‌ها | سامانه حسابداری</b>")
    lines.append(f"📅 <i>{shamsi_today_str}</i>")
    lines.append("")

    # ۱. سررسید امروز
    if today_cheques:
        lines.append("⚠️ <b>سررسید امروز (فوری):</b>")
        for ch in today_cheques:
            is_pay = (ch.type == "PAYABLE" or ch.type == ChequeType.PAYABLE)
            type_icon = "🔴 پرداختی ما" if is_pay else "🟢 دریافتی از مشتری"
            person_name = ch.person.full_name if ch.person else "نامشخص"
            acc_info = ""
            if ch.account:
                bal = ch.account.balance or 0
                acc_info = f"\n   🏦 حساب: {ch.account.title} (مانده: {format_rial(bal)} ریال)"
                if is_pay and bal < (ch.amount or 0):
                    deficit = (ch.amount or 0) - bal
                    acc_info += f" ❗️ <b>کسری موجودی: {format_rial(deficit)} ریال</b>"

            cheque_no = f" | ش.چک: {ch.cheque_number}" if ch.cheque_number else ""
            bank = f" ({ch.bank_name})" if ch.bank_name else ""

            lines.append(
                f"• {type_icon}: <b>{person_name}</b>{bank}{cheque_no}\n"
                f"   💰 مبلغ: <b>{format_rial(ch.amount)} ریال</b>"
                f"{acc_info}"
            )
        lines.append("")

    # ۲. سررسید فردا
    if tomorrow_cheques:
        lines.append("⏳ <b>سررسید فردا (۱ روز مانده):</b>")
        for ch in tomorrow_cheques:
            is_pay = (ch.type == "PAYABLE" or ch.type == ChequeType.PAYABLE)
            type_icon = "🔴 پرداختی" if is_pay else "🟢 دریافتی"
            person_name = ch.person.full_name if ch.person else "نامشخص"
            bank = f" ({ch.bank_name})" if ch.bank_name else ""
            lines.append(
                f"• {type_icon}: <b>{person_name}</b>{bank}\n"
                f"   💰 مبلغ: {format_rial(ch.amount)} ریال"
            )
        lines.append("")

    # ۳. سررسیدهای ۲ الی ۳ روز آینده
    if upcoming_cheques:
        lines.append("📆 <b>سررسیدهای پیش‌رو (تا ۳ روز آینده):</b>")
        for ch in upcoming_cheques:
            is_pay = (ch.type == "PAYABLE" or ch.type == ChequeType.PAYABLE)
            type_icon = "🔴 پرداختی" if is_pay else "🟢 دریافتی"
            person_name = ch.person.full_name if ch.person else "نامشخص"
            days_left = (ch.due_date - today).days
            bank = f" ({ch.bank_name})" if ch.bank_name else ""
            lines.append(
                f"• {type_icon}: <b>{person_name}</b>{bank}\n"
                f"   💰 مبلغ: {format_rial(ch.amount)} ریال | سررسید: {to_jalali_str(ch.due_date)} ({days_left} روز مانده)"
            )
        lines.append("")

    # ۴. معوقه‌ها (سررسید گذشته که پاس یا برگشت نشده)
    if overdue_cheques:
        lines.append("🚨 <b>چک‌های سررسید گذشته (نیاز به پیگیری):</b>")
        for ch in overdue_cheques:
            is_pay = (ch.type == "PAYABLE" or ch.type == ChequeType.PAYABLE)
            type_icon = "🔴 پرداختی" if is_pay else "🟢 دریافتی"
            person_name = ch.person.full_name if ch.person else "نامشخص"
            days_passed = (today - ch.due_date).days
            lines.append(
                f"• {type_icon}: <b>{person_name}</b>\n"
                f"   💰 {format_rial(ch.amount)} ریال | تاریخ: {to_jalali_str(ch.due_date)} ({days_passed} روز پیش)"
            )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("📊 <b>جمع مبالغ سررسید نزدیک:</b>")
    if total_payable > 0:
        lines.append(f"• کل پرداختی شما: <b>{format_rial(total_payable)} ریال</b>")
    if total_receivable > 0:
        lines.append(f"• کل مطالبات دریافتی: <b>{format_rial(total_receivable)} ریال</b>")

    app_domain = getattr(settings, "APP_DOMAIN", None)
    if app_domain:
        domain_url = app_domain.strip().rstrip("/")
        if not domain_url.startswith("http"):
            domain_url = f"https://{domain_url}"
        lines.append(f"\n👉 <a href='{domain_url}/cheques'><b>ورود به سامانه و ثبت وصول چک‌ها</b></a>")
    else:
        lines.append("\n👉 <i>جهت ثبت وصول یا بررسی، به سامانه حسابداری مراجعه فرمایید.</i>")

    return "\n".join(lines)


async def check_and_notify_upcoming_cheques(
    db: Session,
    user_id: Optional[int] = None,
    days_ahead: int = 3,
    force_send: bool = False
) -> Dict[str, Any]:
    """
    بررسی چک‌های نزدیک به سررسید و ارسال هشدار تلگرام
    اگر user_id داده شود، فقط برای آن کاربر بررسی می‌شود (ارسال دستی یا تستی)
    در غیر اینصورت، برای تمام کاربران فعال با شناسه تلگرام بررسی می‌شود (کرون‌جاب دوره‌ای)
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    max_date = today + timedelta(days=days_ahead)

    users_query = db.query(User).filter(User.telegram_chat_id.isnot(None), User.telegram_chat_id != "")
    if user_id:
        users_query = users_query.filter(User.id == user_id)

    users = users_query.all()
    if not users:
        return {
            "success": False,
            "sent_count": 0,
            "cheques_count": 0,
            "message": "کاربری با شناسه تلگرام فعال یافت نشد."
        }

    total_sent = 0
    total_cheques_notified = 0

    for user in users:
        # یافتن چک‌های در انتظار وصول متعلق به کاربر
        query = (
            db.query(Cheque)
            .options(joinedload(Cheque.person), joinedload(Cheque.account))
            .filter(
                Cheque.user_id == user.id,
                Cheque.status == ChequeStatus.PENDING.value,
                Cheque.due_date <= max_date
            )
        )

        # در بررسی خودکار دوره‌ای، اگر امروز برای چکی هشدار رفته باشد، دوباره تکرار نمی‌شود
        if not force_send:
            query = query.filter(
                (Cheque.last_notified_date.is_(None)) | (Cheque.last_notified_date != today)
            )

        cheques = query.order_by(Cheque.due_date.asc()).all()
        if not cheques:
            continue

        today_cheques = [c for c in cheques if c.due_date == today]
        tomorrow_cheques = [c for c in cheques if c.due_date == tomorrow]
        upcoming_cheques = [c for c in cheques if tomorrow < c.due_date <= max_date]
        overdue_cheques = [c for c in cheques if c.due_date < today]

        if not (today_cheques or tomorrow_cheques or upcoming_cheques or overdue_cheques):
            continue

        # تولید پیام تلگرام
        msg = build_cheque_notification_message(
            user=user,
            today=today,
            today_cheques=today_cheques,
            tomorrow_cheques=tomorrow_cheques,
            upcoming_cheques=upcoming_cheques,
            overdue_cheques=overdue_cheques
        )

        # ارسال به تلگرام
        success = await send_telegram_message(user.telegram_chat_id, msg)
        if success:
            total_sent += 1
            total_cheques_notified += len(cheques)
            # ثبت تاریخ آخرین اطلاع‌رسانی
            for ch in cheques:
                ch.last_notified_date = today
            db.commit()

    if total_sent > 0:
        return {
            "success": True,
            "sent_count": total_sent,
            "cheques_count": total_cheques_notified,
            "message": f"یادآور {total_cheques_notified} فقره چک به تلگرام ارسال شد."
        }
    else:
        return {
            "success": True,
            "sent_count": 0,
            "cheques_count": 0,
            "message": "هیچ چک سررسید نزدیکی برای ارسال یافت نشد یا قبلاً اطلاع‌رسانی شده است."
        }
