"""Download a JMComic album and send it as a PDF with ``/jm <id>``."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import jmcomic
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from jmcomic import Feature
from jmcomic.jm_exception import (
    MissingAlbumPhotoException,
    PartialDownloadFailedException,
    RequestRetryAllFailException,
)

TEMP_ROOT = Path("/AstrBot/data/pdf_uploads")
ID_PATTERN = re.compile(r"\d{3,12}")
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _config_int(
    config: AstrBotConfig | dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def parse_cookies(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key:
            cookies[key.strip()] = value.strip()
    return cookies


def normalize_album_id(raw: str) -> str | None:
    candidate = str(raw or "").strip()
    if candidate[:2].lower() == "jm":
        candidate = candidate[2:].strip()
    return candidate if ID_PATTERN.fullmatch(candidate) else None


def safe_pdf_name(album_id: str, title: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", str(title)).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)[:70]
    return f"JM{album_id}-{cleaned}.pdf" if cleaned else f"JM{album_id}.pdf"


def build_option(
    config: AstrBotConfig | dict[str, Any],
    download_dir: Path,
) -> jmcomic.JmOption:
    timeout = _config_int(config, "timeout", 20, 5, 120)
    retry_times = _config_int(config, "retry_times", 3, 1, 10)
    image_threads = _config_int(config, "image_threads", 16, 1, 32)
    photo_threads = _config_int(config, "photo_threads", 4, 1, 16)

    metadata: dict[str, Any] = {"timeout": timeout}
    cookie_values = parse_cookies(str(config.get("cookies", "") or ""))
    if cookie_values:
        metadata["cookies"] = cookie_values

    proxy = str(config.get("proxy", "") or "").strip()
    if proxy:
        if "://" not in proxy:
            proxy = f"http://{proxy}"
        metadata["proxies"] = {"http": proxy, "https": proxy}

    option_dict: dict[str, Any] = {
        "client": {
            "impl": "api",
            "retry_times": retry_times,
            "postman": {"meta_data": metadata},
        },
        "dir_rule": {
            "rule": str(config.get("dir_rule", "") or "Bd / JM{Aid}-{Atitle}"),
            "base_dir": str(download_dir),
        },
        "download": {
            "cache": True,
            "image": {"decode": True, "suffix": ".jpg"},
            "threading": {"image": image_threads, "photo": photo_threads},
        },
    }
    return jmcomic.JmOption.construct(option_dict)


def find_generated_pdf(pdf_dir: Path, album_id: str) -> Path:
    expected = pdf_dir / f"{album_id}.pdf"
    if expected.is_file():
        return expected

    candidates = [path for path in pdf_dir.glob("*.pdf") if path.is_file()]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    raise FileNotFoundError("PDF 转换没有产生输出文件")


def validate_pdf(pdf_path: Path) -> None:
    """Reject empty or mislabeled output before it reaches QQ."""
    if not pdf_path.is_file() or pdf_path.stat().st_size < 1024:
        raise ValueError("生成的 PDF 文件为空或过小")
    with pdf_path.open("rb") as file_handle:
        if file_handle.read(5) != b"%PDF-":
            raise ValueError("生成文件不是有效的 PDF")


async def upload_pdf_to_qq(
    event: AstrMessageEvent,
    pdf_path: Path,
    file_name: str,
) -> object:
    """Upload a real QQ file through NapCat's OneBot actions."""
    group_id = event.get_group_id()
    if group_id:
        return await event.bot.api.call_action(
            "upload_group_file",
            group_id=int(group_id),
            file="file://" + str(pdf_path.resolve()),
            name=file_name,
        )
    return await event.bot.api.call_action(
        "upload_private_file",
        user_id=int(event.get_sender_id()),
        file="file://" + str(pdf_path.resolve()),
        name=file_name,
    )


@register(
    "jmdownloader",
    "CLRedfield",
    "使用 /jm <ID> 下载 JMComic 漫画并发送 PDF",
    "1.0.3",
)
class JMDownloaderPlugin(Star):
    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__(context)
        self.config = config or {}
        max_concurrent = _config_int(self.config, "max_concurrent", 1, 1, 3)
        self.download_semaphore = asyncio.Semaphore(max_concurrent)
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_jobs()

    def _cleanup_stale_jobs(self) -> None:
        cutoff = time.time() - 3600
        try:
            children = list(TEMP_ROOT.iterdir())
        except OSError:
            return
        for path in children:
            try:
                if path.is_dir() and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                continue

    @filter.command("jm", desc="下载 JMComic 漫画并发送 PDF：/jm <数字ID>")
    async def download_command(self, event: AstrMessageEvent, jm_id: str = ""):
        event.stop_event()

        if not self.config.get("enabled", True):
            yield event.plain_result("JM 下载插件当前已关闭。")
            return

        album_id = normalize_album_id(jm_id)
        if album_id is None:
            yield event.plain_result("用法：/jm <数字ID>，例如 /jm 123456")
            return

        if event.get_group_id() and not self.config.get("allow_group", True):
            yield event.plain_result("JM 下载当前仅允许在私聊中使用。")
            return

        if self.download_semaphore.locked():
            await event.send(
                MessageChain().message(f"JM{album_id} 已加入下载队列，请稍候……"),
            )

        async with self.download_semaphore:
            await event.send(
                MessageChain().message(
                    f"开始下载 JM{album_id}，完成后会直接发送 PDF。",
                ),
            )
            self._cleanup_stale_jobs()
            job_root = Path(
                tempfile.mkdtemp(prefix=f"jm{album_id}-", dir=str(TEMP_ROOT)),
            )
            job_root.chmod(0o755)
            download_dir = job_root / "download"
            pdf_dir = job_root / "pdf"
            download_dir.mkdir(parents=True, exist_ok=True)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            download_dir.chmod(0o755)
            pdf_dir.chmod(0o755)
            try:
                option = build_option(self.config, download_dir)
                self.logger.info("Starting JMComic download: JM%s", album_id)
                result = await asyncio.to_thread(
                    jmcomic.download_album,
                    album_id,
                    option,
                    extra=Feature.export_pdf(
                        pdf_dir=str(pdf_dir),
                        filename_rule="Aid",
                        delete_original_file=True,
                    ),
                )

                album = result.detail
                resolved_id = str(album.id)
                pdf_path = find_generated_pdf(pdf_dir, resolved_id)
                validate_pdf(pdf_path)
                file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
                self.logger.info(
                    "JMComic PDF ready: JM%s, %.2f MiB, %s",
                    resolved_id,
                    file_size_mb,
                    pdf_path,
                )

                pdf_name = safe_pdf_name(resolved_id, str(album.name))
                try:
                    upload_result = await upload_pdf_to_qq(
                        event,
                        pdf_path,
                        pdf_name,
                    )
                except Exception:
                    self.logger.exception(
                        "QQ PDF upload failed: JM%s, %s",
                        resolved_id,
                        pdf_path,
                    )
                    yield event.plain_result(
                        f"JM{resolved_id} 已生成 PDF，但 QQ 文件上传失败。"
                        "请检查机器人是否有群文件上传权限；详细原因已写入 AstrBot 日志。",
                    )
                    return

                self.logger.info(
                    "QQ PDF upload completed: JM%s, result=%r",
                    resolved_id,
                    upload_result,
                )
                yield event.plain_result(
                    f"JM{resolved_id} PDF 已作为 QQ 文件上传（{file_size_mb:.2f} MiB）。",
                )
            except MissingAlbumPhotoException:
                self.logger.warning("JMComic album was not found: JM%s", album_id)
                yield event.plain_result(
                    f"没有找到 JM{album_id}。请检查 ID；若它仅登录可见，请在插件配置中填写 cookies。",
                )
            except RequestRetryAllFailException:
                self.logger.exception("JMComic network request failed: JM%s", album_id)
                yield event.plain_result(
                    "JMComic 站点连接失败。请稍后重试，或在插件配置中设置可用代理。",
                )
            except PartialDownloadFailedException:
                self.logger.exception("JMComic partial download failed: JM%s", album_id)
                yield event.plain_result(
                    "部分图片下载失败，未发送不完整的 PDF，请稍后重试。"
                )
            except Exception as exc:
                self.logger.exception("JMComic download failed: JM%s", album_id)
                yield event.plain_result(
                    f"JM{album_id} 下载失败（{type(exc).__name__}）。详细原因已写入 AstrBot 日志。",
                )
            finally:
                async def delayed_cleanup():
                        await asyncio.sleep(600)
                        shutil.rmtree(job_root, ignore_errors=True)
                        asyncio.create_task(delayed_cleanup())
                pass
                