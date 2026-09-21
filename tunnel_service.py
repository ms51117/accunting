import asyncio
import logging
import re
import shutil
import sys
import httpx
from datetime import datetime
import jdatetime

from app.config import settings
from app.database import SessionLocal
from app.models.user import User

logger = logging.getLogger("cloudflare_tunnel")


class CloudflareTunnelService:
    def __init__(self):
        self.bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or getattr(settings, "telegram_bot_token", None)
        self.is_enabled = getattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", True)
        self.port = getattr(settings, "APP_PORT", 8000)
        self.last_url = None

    async def _send_telegram(self, chat_id: str, message: str) -> bool:
        if not self.bot_token or not chat_id:
            logger.warning("Bot token or chat_id is missing.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return True
                logger.error(f"Telegram API Error ({res.status_code}): {res.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            return False

    async def notify_users(self, new_url: str):
        shamsi_now = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")

        db = SessionLocal()
        try:
            users = db.query(User).filter(
                User.telegram_chat_id.isnot(None),
                User.telegram_chat_id != ""
            ).all()

            if not users:
                logger.warning("No users with valid telegram_chat_id found in database.")
                return

            for user in users:
                role_label = "👑 مدیر" if getattr(user, 'is_admin', False) else "👤 کاربر"
                user_name = getattr(user, 'full_name', None) or getattr(user, 'username', 'کاربر')

                msg = (
                    f"🚀 <b>سامانه حسابداری آنلاین شد</b>\n\n"
                    f"سلام {user_name} عزیز ({role_label})\n"
                    f"لینک جدید و موقت سرور کلودفلر آماده استفاده است:\n\n"
                    f"🔗 <a href='{new_url}'>{new_url}</a>\n\n"
                    f"📅 زمان ایجاد: <code>{shamsi_now}</code>\n"
                    f"⚠️ <i>این لینک تا ریستارت بعدی سرور فعال خواهد بود.</i>"
                )
                await self._send_telegram(user.telegram_chat_id, msg)
                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Database error while fetching users for notification: {e}")
        finally:
            db.close()

    async def start(self):
        if not self.is_enabled:
            logger.info("Cloudflare Tunnel is disabled in config.")
            return

        # تشخیص باینری ویندوز یا لینوکس
        binary_name = "cloudflared.exe" if sys.platform.startswith("win") else "cloudflared"
        executable = shutil.which(binary_name) or shutil.which(f"./{binary_name}")

        if not executable:
            logger.error(
                f"Cloudflare binary '{binary_name}' not found. Please put '{binary_name}' in project directory.")
            return

        url_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
        cmd = f"{executable} tunnel --url http://127.0.0.1:{self.port}"

        while True:
            try:
                logger.info(f"Starting Cloudflare Tunnel on port {self.port}...")
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    decoded_line = line.decode('utf-8', errors='ignore').strip()
                    match = url_pattern.search(decoded_line)

                    if match:
                        extracted_url = match.group(0)
                        if extracted_url != self.last_url:
                            self.last_url = extracted_url
                            logger.info(f"⚡ Cloudflare Public URL: {extracted_url}")
                            asyncio.create_task(self.notify_users(extracted_url))

                logger.warning("Cloudflare tunnel process terminated. Restarting in 7 seconds...")
                await asyncio.sleep(7)

            except asyncio.CancelledError:
                logger.info("Stopping Cloudflare Tunnel...")
                if 'process' in locals() and process.returncode is None:
                    process.terminate()
                break
            except Exception as e:
                logger.error(f"Unexpected error in tunnel service: {e}")
                await asyncio.sleep(7)


tunnel_service = CloudflareTunnelService()
