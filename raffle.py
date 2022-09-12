import os
import re
import sys
import json
import string
import random
import asyncio
import platform
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import discord
from rich import print
from rich.progress import track


# dyno = 347378323418251264
# pandez_tools = 941115891247116409
# giveaway_boat = 530082442967646230
# invite_tracker = 720351927581278219
# giveaway_bot = 294882584201003009

KEYWORDS = [
    "giveaway",
    "raffle",
    "抽奖",
    # "collab",
    "bless",
    "whitelist",
    "partnership",
]
NON_KEYWORDS = (
    "request",
    "join",
    "nomination",
    "config",
    "mod",
    "chat",
    "event",
    "faq",
    "rules",
    "how",
    "addresses",
    "details",
    "news",
    "voting",
    "team",
    "ticket",
    "suggestions",
    "submit",
    "register",
    "link",
    "info",
    "competition",
    "twitter",
    "winner",
    "manager",
    "promotion",
    "contest",
    "rumble",
    "royale",
    "results",
    "discussion",
    "announcement",
    "简介",
)

setattr(asyncio.sslproto._SSLProtocolTransport, "_start_tls_compatible", True)

if getattr(sys, "frozen", False):
    os.environ["SSL_CERT_FILE"] = os.path.join(sys._MEIPASS, "lib", "cert.pem")


async def fetch_guilds(self):
    data = await self.http.get_guilds(limit=200)
    for raw_guild in data:
        yield discord.Guild(state=self._connection, data=raw_guild)


# Monkey patching `fetch_guilds` method since there is a bug
discord.Client.fetch_guilds = fetch_guilds


def print_time(data):
    print(
        f'[light_steel_blue1]{datetime.now().strftime("%m-%d %H:%M:%S")}[/light_steel_blue1] {data}'
    )


def random_string(length):
    asciis = string.ascii_lowercase + string.digits
    return "".join(random.sample(asciis, length))


def is_raffle_channel(channel):
    return (
        channel.type in [discord.ChannelType.text, discord.ChannelType.news]
        and channel.last_message_id is not None
        and any(word in channel.name.lower() for word in KEYWORDS)
        and all(word not in channel.name.lower() for word in NON_KEYWORDS)
    )


async def record_winner(client, message):
    guild_name = message.guild.name
    guild_id = message.guild.id
    channel_name = message.channel.name
    channel_id = message.channel.id

    # console output
    print_time(
        f"[light_pink1]{client.user.name}[/light_pink1] 中奖 [red1]{guild_name}[/red1] - [light_goldenrod1]{channel_name}[/light_goldenrod1]"
        f"\n中奖消息链接: https://discord.com/channels/{guild_id}/{channel_id}/{message.id}"
    )

    # save to file
    msg = f"{guild_name} - {channel_name}: https://discord.com/channels/{guild_id}/{channel_id}/{message.id}"
    with open(f"raffle_result.txt", mode="a", encoding="utf-8") as f:
        f.write(f"{client.user.name}#{client.user.discriminator} - {msg}\n")

    # discord notify
    if hasattr(client, "notify_channel"):
        await client.notify_channel.send(content=f"<@!{client.user.id}> {msg}")


async def handle_normal_raffle(client, message):
    embed = message.embeds[0]
    if not embed.description:
        return
    if "react with" not in embed.description.lower():
        return

    symbol = re.findall("react with (.)", embed.description, re.I)[0]

    for reaction in message.reactions:
        if reaction.emoji == symbol and reaction.me:
            return

    project = None
    if embed.author:
        project = embed.author.name
    elif embed.title:
        project = embed.title.replace("\n", " ").replace(
            "<a:blobgift:834855281358930020>", ""
        )
    if project is None:
        project = "Unknown"

    await message.add_reaction(symbol)
    print_time(
        f"[light_pink1]{client.user.name}[/light_pink1] 参与抽奖 [violet]{message.guild.name}[/violet] - [light_sky_blue1]{message.channel.name}[/light_sky_blue1] - [pale_green1]{project}[/pale_green1]"
    )


async def handle_components_raffle(client, message):
    component = message.components[0].children[0]

    label = getattr(component, "label", "")
    if label and "enter" not in label.lower():
        return

    custom_id = component.custom_id
    if custom_id is None:
        return

    embed = message.embeds[0]
    project = ""
    if embed.description:
        matches = re.findall("\*\*Prize:\*\*(.*?)\n", embed.description)
        project = matches[0].strip() if matches else ""

    if project == "":
        project = message.embeds[0].title

    if "application_id" in message.data:
        application_id = message.data["application_id"]
    else:
        application_id = message.author.id

    data = {
        "application_id": application_id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id,
        "data": {"component_type": 2, "custom_id": custom_id},
        "message_id": message.id,
        "type": 3,
        "session_id": client.session_id,
    }
    route = discord.http.Route("POST", "/interactions")
    await client.http.request(route, json=data)

    print_time(
        f"[light_pink1]{client.user.name}[/light_pink1] 参与抽奖 [violet]{message.guild.name}[/violet] - [light_sky_blue1]{message.channel.name}[/light_sky_blue1] - [pale_green1]{project}[/pale_green1]"
    )


async def workflow(client):
    guilds = [guild async for guild in client.fetch_guilds()]
    for guild in track(guilds, description=client.user.name, transient=True):
        client._connection._add_guild(guild)

        channels = await guild.fetch_channels()
        for channel in channels:

            if not is_raffle_channel(channel):
                continue

            last_msg_id = client.last_msg_id_record[channel.id]
            if last_msg_id == channel.last_message_id:
                continue

            after = discord.Object(id=last_msg_id) if last_msg_id != 0 else None
            try:
                async for message in channel.history(limit=20, after=after):
                    client.last_msg_id_record[channel.id] = message.id

                    if not message.author.bot:
                        continue

                    if "congrat" in message.content.lower():
                        if str(client.user.id) in message.content:
                            await record_winner(client, message)
                        continue

                    if not message.embeds:
                        continue

                    if message.components:
                        await handle_components_raffle(client, message)
                    else:
                        await handle_normal_raffle(client, message)

            except (discord.errors.NotFound, discord.errors.Forbidden) as e:
                continue


async def main(args):
    clients = []

    with args.auth_file.open() as f:
        for token in f:
            intents = discord.Intents.default()
            intents.message_content = True
            client = discord.Client(
                max_messages=None, intents=intents, proxy="socks5://127.0.0.1:7890"
            )
            client.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
            await client.login(token.strip())
            print_time(f"获取到用户: [light_pink1]{client.user.name}[/light_pink1]")

            client.session_id = random_string(32)

            state_file = f"state_{client.user.id}.json"
            path = Path(state_file)
            client.last_msg_id_record = defaultdict(int)
            if path.exists():
                with path.open() as f:
                    data = json.load(f)
                    client.last_msg_id_record.update(
                        {int(k): int(v) for k, v in data.items()}
                    )

            if args.notify_channel:
                client.notify_channel = await client.fetch_channel(args.notify_channel)

            clients.append(client)

    while True:
        try:
            for client in clients:
                await workflow(client)

            if args.interval:
                await asyncio.sleep(args.interval)
            else:
                break
        except asyncio.CancelledError:
            break

    for client in clients:
        await client.http.close()
        state_file = f"state_{client.user.id}.json"
        with open(state_file, "w") as f:
            json.dump(client.last_msg_id_record, f)
            print_time(
                f"用户 [light_pink1]{client.user.name}[/light_pink1] 状态保存为 [orange1]{state_file}[/orange1] 「请勿做任何修改」"
            )


def get_parser(prog):
    parser = argparse.ArgumentParser(
        prog=prog,
        epilog="Copyright by 0xshimmer.eth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"""Discord 自动抽奖机器人

    提供多账号执行及定时执行功能，使用样例如下:

    # 多账号执行，提供保存有账号 auth 值的 txt 文件
    {prog} --auth-file auth.txt

    # 定时执行，每隔 interval 秒重新运行一次
    # 如每 5 分钟运行一次
    {prog} --auth-file auth.txt --interval 300

    # 输出中奖信息到 DC
     {prog} --auth-file auth.txt --interval 300 --notify-channel 921638353538007040

    # 添加自定义关键词 collab 和 partnership
    {prog} --auth-file auth.txt --keywords collab,partnership
        """,
    )
    parser.add_argument(
        "--auth-file",
        dest="auth_file",
        metavar="filename",
        type=Path,
        help="保存所有用户 Token 的文件，用于多用户进行抽奖",
    )
    parser.add_argument(
        "--interval",
        dest="interval",
        metavar="minutes",
        help="下一次运行的时间间隔",
        type=int,
    )
    parser.add_argument(
        "--notify-channel", dest="notify_channel", metavar="channelID", help="中奖通知频道"
    )
    parser.add_argument(
        "--keywords", dest="keywords", metavar="keywords", help="自定义关键词，以英文逗号分开"
    )
    return parser


if __name__ == "__main__":
    prog = "raffle"
    if platform.system() == "Windows":
        prog = "raffle.exe"

    parser = get_parser(prog)
    args = parser.parse_args()

    if not args.auth_file:
        parser.error(f"需指定 auth 或者 auth-file 参数\n\n输入 {prog} -h 获取帮助文档")

    if args.keywords:
        for kw in args.keywords.split(","):
            if kw not in KEYWORDS:
                KEYWORDS.append(kw)

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
