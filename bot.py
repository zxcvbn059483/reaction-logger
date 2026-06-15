import discord
import json
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.getenv("TOKEN")

TARGET_CHANNEL_ID = 1375102819673313380
LOG_CHANNEL_ID = 1515550120727543919

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler()


def load_data():
    try:
        with open("user_activity.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data):
    with open("user_activity.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_activity(user_id, guild_id, channel_id, message_id, emoji):
    data = load_data()
    user_id = str(user_id)

    now = datetime.now().isoformat()

    message_url = (
        f"https://discord.com/channels/"
        f"{guild_id}/{channel_id}/{message_id}"
    )

    if user_id not in data:
        data[user_id] = {
            "last_activity": now,
            "reaction_count": 1,
            "last_emoji": str(emoji),
            "last_message_url": message_url,
            "last_message_id": str(message_id),
            "last_channel_id": str(channel_id)
        }

    else:
        # 예전 형식 데이터가 문자열로 저장되어 있을 경우 자동 변환
        if isinstance(data[user_id], str):
            data[user_id] = {
                "last_activity": data[user_id],
                "reaction_count": 0
            }

        data[user_id]["last_activity"] = now

        data[user_id]["reaction_count"] = (
            data[user_id].get("reaction_count", 0) + 1
        )

        data[user_id]["last_emoji"] = str(emoji)
        data[user_id]["last_message_url"] = message_url
        data[user_id]["last_message_id"] = str(message_id)
        data[user_id]["last_channel_id"] = str(channel_id)

    save_data(data)


async def check_inactive_users():
    target_channel = client.get_channel(TARGET_CHANNEL_ID)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if target_channel is None:
        print("감시 채널을 찾을 수 없습니다.")
        return

    if log_channel is None:
        print("로그 채널을 찾을 수 없습니다.")
        return

    guild = target_channel.guild

    data = load_data()
    inactive_users = []

    for member in guild.members:
        # 봇은 검사하지 않음
        if member.bot:
            continue

        # @everyone 역할만 가진 사람만 검사
        if len(member.roles) > 1:
            continue

        user_id = str(member.id)

        # 반응 기록이 한 번도 없는 사람은 표시하지 않음
        if user_id not in data:
            continue

        user_data = data[user_id]

        # 예전 형식 데이터 대응
        if isinstance(user_data, str):
            last_activity = datetime.fromisoformat(user_data)
        else:
            last_activity = datetime.fromisoformat(
                user_data["last_activity"]
            )

        days = (datetime.now() - last_activity).days

        # 14일 이상 반응이 없는 사람만 추가
        if days >= 14:
            if isinstance(user_data, dict):
                last_emoji = user_data.get(
                    "last_emoji",
                    "기록 없음"
                )

                last_message_url = user_data.get(
                    "last_message_url",
                    "기록 없음"
                )

                inactive_users.append(
                    f"{member.display_name} ({days}일)\n"
                    f"마지막 이모지: {last_emoji}\n"
                    f"마지막으로 반응한 글: {last_message_url}\n"
                )

            else:
                inactive_users.append(
                    f"{member.display_name} ({days}일)\n"
                    f"마지막 이모지: 기록 없음\n"
                    f"마지막으로 반응한 글: 기록 없음\n"
                )

    if inactive_users:
        msg = "📢 역할 없는 14일 이상 미반응자\n\n"
        msg += "\n".join(inactive_users)
    else:
        msg = (
            "📢 역할 없는 14일 이상 미반응자\n\n"
            "없음"
        )

    await log_channel.send(msg)


async def send_reaction_ranking():
    target_channel = client.get_channel(TARGET_CHANNEL_ID)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if target_channel is None:
        print("감시 채널을 찾을 수 없습니다.")
        return

    if log_channel is None:
        print("로그 채널을 찾을 수 없습니다.")
        return

    guild = target_channel.guild

    data = load_data()
    ranking = []

    for user_id, info in data.items():
        member = guild.get_member(int(user_id))

        if member is None:
            continue

        if isinstance(info, str):
            count = 0
        else:
            count = info.get("reaction_count", 0)

        ranking.append(
            (member.display_name, count)
        )

    ranking.sort(
        key=lambda x: x[1],
        reverse=True
    )

    current = datetime.now()
    target_month = current.month - 1
    target_year = current.year

    if target_month == 0:
        target_month = 12
        target_year -= 1

    msg = (
        f"🏆 {target_year}년 "
        f"{target_month}월 반응 TOP10\n\n"
    )

    if ranking:
        for i, (name, count) in enumerate(
            ranking[:10],
            start=1
        ):
            msg += f"{i}위 - {name} ({count}회)\n"
    else:
        msg += "기록 없음"

    await log_channel.send(msg)

    # 월간 반응 횟수만 초기화
    # 마지막 반응 시간과 메시지 링크는 유지
    for user_id in data:
        if isinstance(data[user_id], dict):
            data[user_id]["reaction_count"] = 0

    save_data(data)


@client.event
async def on_ready():
    print(f"로그인 완료 : {client.user}")

    # 봇이 재연결됐을 때 스케줄러가 중복 실행되는 것을 방지
    if not scheduler.running:

        # 매일 00:00 미반응자 검사
        scheduler.add_job(
            check_inactive_users,
            "cron",
            hour=0,
            minute=0,
            id="check_inactive_users",
            replace_existing=True
        )

        # 매월 1일 00:01 월간 TOP10 출력
        scheduler.add_job(
            send_reaction_ranking,
            "cron",
            day=1,
            hour=0,
            minute=1,
            id="send_reaction_ranking",
            replace_existing=True
        )

        scheduler.start()


@client.event
async def on_raw_reaction_add(payload):
    # 지정된 채널의 반응만 기록
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    guild = client.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if member is None:
        return

    # 봇이 누른 반응은 기록하지 않음
    if member.bot:
        return

    if log_channel is None:
        return

    # 마지막 반응 시간, 이모지, 메시지 링크 저장
    save_activity(
        payload.user_id,
        payload.guild_id,
        payload.channel_id,
        payload.message_id,
        payload.emoji
    )

    # 평소 반응 추가 메시지에는 링크를 표시하지 않음
    await log_channel.send(
        f"✅ 반응 추가\n"
        f"사용자: {member.display_name}\n"
        f"이모지: {payload.emoji}"
    )


@client.event
async def on_raw_reaction_remove(payload):
    # 지정된 채널의 반응만 기록
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    guild = client.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if member is None:
        return

    if member.bot:
        return

    if log_channel is None:
        return

    await log_channel.send(
        f"❌ 반응 제거\n"
        f"사용자: {member.display_name}\n"
        f"이모지: {payload.emoji}"
    )


client.run(TOKEN)