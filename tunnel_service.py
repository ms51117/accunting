import asyncio
import logging
import re
import shutil
import httpx
from datetime import datetime
import jdatetime

from app.config import settings
from app.database import SessionLocal
from app.models.user import User  # در صورت استفاده از پکیج app: from app.models.user import User

logger = logging.getLogger("cloudflare_tunnel")


class CloudflareTunnelService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.proxy = settings.https_proxy or settings.http_proxy
        self.is_enabled = settings.CLOUDFLARE_TUNNEL_ENABLED
        self.port = settings.APP_PORT
        self.last_url = None

    async def _send_telegram(self, chat_id: str, message: str) -> bool:
        """ارسال پیام تلگرام از طریق بات پروژه با پشتیبانی کامل از پروکسی"""
        if not self.bot_token:
            logger.warning("[Telegram] bot_token تنظیم نشده است.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            # سازگار با نسخه‌های جدید httpx
            async with httpx.AsyncClient(proxy=self.proxy, timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                logger.error(f"[Telegram] خطا در ارسال به {chat_id}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] خطای شبکه در ارسال به {chat_id}: {e}")
            return False

    async def notify_users(self, tunnel_url: str):
        """خواندن کاربران دارای telegram_chat_id از دیتابیس و ارسال آدرس جدید"""
        now_shamsi = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")

        db = SessionLocal()
        try:
            # دریافت کاربرانی که شناسه تلگرام دارند
            users = db.query(User).filter(
                User.telegram_chat_id.isnot(None),
                User.telegram_chat_id != ""
            ).all()

            if not users:
                logger.info("[Tunnel] کاربری با telegram_chat_id در دیتابیس یافت نشد.")
                return

            for user in users:
                display_name = user.full_name or user.username
                role_badge = "👑 <b>مدیر سیستم</b>" if getattr(user, "is_admin", False) else "👤 <b>کاربر گرامی</b>"

                msg = (
                    f"🚀 <b>سامانه {settings.APP_NAME} آنلاین شد</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{role_badge}: <b>{display_name}</b>\n\n"
                    f"🌐 <b>لینک ورود مستقیم (بدون نیاز به فیلترشکن):</b>\n"
                    f"👉 <a href='{tunnel_url}'>{tunnel_url}</a>\n\n"
                    f"📅 زمان ایجاد: <code>{now_shamsi}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>در صورت راه‌اندازی مجدد سرور، لینک جدید به صورت خودکار برای شما ارسال خواهد شد.</i>"
                )

                success = await self._send_telegram(user.telegram_chat_id, msg)
                if success:
                    logger.info(f"[Tunnel] لینک با موفقیت برای {user.username} ارسال شد.")
        except Exception as e:
            logger.error(f"[Tunnel] خطای دیتابیس در خواندن کاربران: {e}")
        finally:
            db.close()

    async def start(self):
        """اجرای cloudflared و استخراج داینامیک URL"""
        if not self.is_enabled:
            logger.info("[Tunnel] کلودفلر تونل در تنظیمات غیرفعال است.")
            return

        if not shutil.which("cloudflared"):
            logger.error("[Tunnel] ابزار cloudflared روی سرور/کانتینر نصب نیست.")
            return

        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        cmd = ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self.port}"]

        while True:
            try:
                logger.info(f"[Tunnel] در حال اجرای Cloudflare Tunnel روی پورت {self.port}...")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while not proc.stdout.at_eof():
                    line = (await proc.stdout.readline()).decode(errors="ignore")
                    if not line:
                        break

                    match = url_pattern.search(line)
                    if match:
                        new_url = match.group(0)
                        if new_url != self.last_url:
                            self.last_url = new_url
                            logger.info(f"✨ [Tunnel] آدرس فعال شد: {new_url}")
                            # ارسال نوتیفیکیشن به کاربران
                            asyncio.create_task(self.notify_users(new_url))

                await proc.wait()
                logger.warning("[Tunnel] پروسس متوقف شد. تلاش مجدد در ۷ ثانیه...")
                await asyncio.sleep(7)

            except asyncio.CancelledError:
                if proc:
                    proc.terminate()
                break
            except Exception as e:
                logger.error(f"[Tunnel] خطای ران‌تایم: {e}")
                await asyncio.sleep(7)


# نمونه سراسری
tunnel_service = CloudflareTunnelService()
