from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove
from asyncio import gather, create_subprocess_exec
from os import execl as osexecl
from psutil import (
    disk_usage,
    cpu_percent,
    swap_memory,
    cpu_count,
    virtual_memory,
    net_io_counters,
    boot_time,
)
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler
from signal import signal, SIGINT
from sys import executable
from time import time

from bot import (
    bot,
    botStartTime,
    LOGGER,
    Intervals,
    DATABASE_URL,
    INCOMPLETE_TASK_NOTIFIER,
    scheduler,
)
from .helper.ext_utils.bot_utils import cmd_exec, sync_to_async, create_help_buttons
from .helper.ext_utils.db_handler import DbManager
from .helper.ext_utils.files_utils import clean_all, exit_clean_up
from .helper.ext_utils.status_utils import get_readable_file_size, get_readable_time
from .helper.ext_utils.telegraph_helper import telegraph
from .helper.listeners.aria2_listener import start_aria2_listener
from .helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
from .helper.telegram_helper.bot_commands import BotCommands
from .helper.telegram_helper.button_build import ButtonMaker
from .helper.telegram_helper.filters import CustomFilters
from .helper.telegram_helper.message_utils import sendMessage, editMessage, sendFile
from .modules.func import *
from .modules import (
    authorize,
    broadcast,
    cancel_task,
    clone,
    exec,
    gd_count,
    gd_delete,
    gd_search,
    mirror_leech,
    status,
    torrent_search,
    torrent_select,
    ytdlp,
    rss,
    shell,
    users_settings,
    bot_settings,
    help,
    force_start,
    welcome
)


async def restart(_, message):
    Intervals["stopAll"] = True
    restart_message = await sendMessage(message, "Restarting...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if qb := Intervals["qb"]:
        qb.cancel()
    if st := Intervals["status"]:
        for intvl in list(st.values()):
            intvl.cancel()
    await sync_to_async(clean_all)
    proc1 = await create_subprocess_exec(
        "pkill", "-9", "-f", "gunicorn|xygrep|xyuren|xytool|xyfetch"
    )
    proc2 = await create_subprocess_exec("python3", "update.py")
    await gather(proc1.wait(), proc2.wait())
    async with aiopen(".restartmsg", "w") as f:
        await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
    osexecl(executable, executable, "-m", "bot")


async def ping(_, message):
    start_time = int(round(time() * 1000))
    reply = await sendMessage(message, "Starting Ping")
    end_time = int(round(time() * 1000))
    await editMessage(reply, f"{end_time - start_time} ms")


async def log(_, message):
    await sendFile(message, "log.txt")


help_string = f"""
NOTE: Try each command without any argument to see more detalis.
/{BotCommands.MirrorCommand[0]}: Start mirroring to Google Drive.
/{BotCommands.QbMirrorCommand[0]}: Start Mirroring to Google Drive using qBittorrent.
/{BotCommands.YtdlCommand[0]}: Mirror yt-dlp supported link.
/{BotCommands.LeechCommand[0]}: Start leeching to Telegram.
/{BotCommands.QbLeechCommand[0]}: Start leeching using qBittorrent.
/{BotCommands.YtdlLeechCommand[0]}: Leech yt-dlp supported link.
/{BotCommands.CloneCommand} [drive_url]: Copy file/folder to Google Drive.
/{BotCommands.CountCommand} [drive_url]: Count file/folder of Google Drive.
/{BotCommands.DeleteCommand} [drive_url]: Delete file/folder from Google Drive (Only Owner & Sudo).
/{BotCommands.UserSetCommand[0]} [query]: Users settings.
/{BotCommands.BotSetCommand[0]} [query]: Bot settings.
/{BotCommands.BtSelectCommand}: Select files from torrents by gid or reply.
/{BotCommands.CancelTaskCommand[0]} [gid]: Cancel task by gid or reply.
/{BotCommands.ForceStartCommand[0]} [gid]: Force start task by gid or reply.
/{BotCommands.CancelAllCommand} [query]: Cancel all [status] tasks.
/{BotCommands.ListCommand} [query]: Search in Google Drive(s).
/{BotCommands.SearchCommand} [query]: Search for torrents with API.
/{BotCommands.StatusCommand}: Shows a status of all the downloads.
/{BotCommands.StatsCommand}: Show stats of the machine where the bot is hosted in.
/{BotCommands.PingCommand}: Check how long it takes to Ping the Bot (Only Owner & Sudo).
/{BotCommands.AuthorizeCommand}: Authorize a chat or a user to use the bot (Only Owner & Sudo).
/{BotCommands.UnAuthorizeCommand}: Unauthorize a chat or a user to use the bot (Only Owner & Sudo).
/{BotCommands.UsersCommand}: show users settings (Only Owner & Sudo).
/{BotCommands.AddSudoCommand}: Add sudo user (Only Owner).
/{BotCommands.RmSudoCommand}: Remove sudo users (Only Owner).
/{BotCommands.RestartCommand}: Restart and update the bot (Only Owner & Sudo).
/{BotCommands.LogCommand}: Get a log file of the bot. Handy for getting crash reports (Only Owner & Sudo).
/{BotCommands.ShellCommand}: Run shell commands (Only Owner).
/{BotCommands.AExecCommand}: Exec async functions (Only Owner).
/{BotCommands.ExecCommand}: Exec sync functions (Only Owner).
/{BotCommands.ClearLocalsCommand}: Clear {BotCommands.AExecCommand} or {BotCommands.ExecCommand} locals (Only Owner).
/{BotCommands.RssCommand}: RSS Menu.
"""


async def bot_help(_, message):
    await sendMessage(message, help_string)


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
    else:
        chat_id, msg_id = 0, 0

    async def send_incompelete_task_message(cid, msg):
        try:
            if msg.startswith("Restarted Successfully!"):
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id, text=msg
                )
                await remove(".restartmsg")
            else:
                await bot.send_message(
                    chat_id=cid,
                    text=msg,
                    disable_web_page_preview=True,
                    disable_notification=True,
                )
        except Exception as e:
            LOGGER.error(e)

    if INCOMPLETE_TASK_NOTIFIER and DATABASE_URL:
         if notifier_dict := await DbManager().get_incomplete_tasks():
            for cid, data in notifier_dict.items():
                msg = "Restarted Successfully!" if cid == chat_id else "Bot Restarted!"
                for tag, links in data.items():
                    msg += f"\n\n{tag}: "
                    for index, link in enumerate(links, start=1):
                        msg += f" <a href='{link}'>{index}</a> |"
                        if len(msg.encode()) > 4000:
                            await send_incompelete_task_message(cid, msg)
                            msg = ""
                if msg:
                    await send_incompelete_task_message(cid, msg)

    if await aiopath.isfile(".restartmsg"):
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text="Restarted Successfully!"
            )
        except:
            pass
        await remove(".restartmsg")


async def main():
    await gather(sync_to_async(clean_all), torrent_search.initiate_search_tools(), restart_notification(), telegraph.create_account(), rclone_serve_booter(), sync_to_async(start_aria2_listener, wait=False), set_commands(bot))
    create_help_buttons()
    bot.add_handler(
        MessageHandler(
            restart, filters=command(BotCommands.RestartCommand) & CustomFilters.sudo
        )
    )
    bot.add_handler(
        MessageHandler(
            ping, filters=command(BotCommands.PingCommand) & CustomFilters.authorized
        )
    )
    bot.add_handler(
        MessageHandler(
            bot_help,
            filters=command(BotCommands.HelpCommand) & CustomFilters.authorized,
        )
    )
    LOGGER.info("Bot Started!")
    signal(SIGINT, exit_clean_up)


bot.loop.run_until_complete(main())
bot.loop.run_forever()
