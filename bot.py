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


def load_data():
    try:
        with open("user_activity.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_data(data):
    with open("user_activity.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_activity(user_id):
    data = load_data()
    user_id = str(user_id)

    if user_id not in data:
        data[user_id] = {
            "last_activity": datetime.now().isoformat(),
            "reaction_count": 1
        }
    else:
        # 예전 형식 데이터가 남아 있을 경우 자동 변환
        if isinstance(data[user_id], str):
            data[user_id] = {
                "last_activity": data[user_id],
                "reaction_count": 0
            }

        data[user_id]["last_activity"] = datetime.now().isoformat()
        data[user_id]["reaction_count"] = data[user_id].get("reaction_count", 0) + 1

    save_data(data)


async def check_inactive_users():
    guild = client.guilds[0]
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    data = load_data()
    inactive_users = []

    for member in guild.members:
        if member.bot:
            continue

        # @everyone만 가진 사람만 검사
        if len(member.roles) > 1:
            continue

        user_id = str(member.id)

        if user_id not in data:
            inactive_users.append(f"{member.display_name} (반응 기록 없음)")
            continue

        # 예전 형식 데이터 대응
        if isinstance(data[user_id], str):
            last_activity = datetime.fromisoformat(data[user_id])
        else:
            last_activity = datetime.fromisoformat(data[user_id]["last_activity"])

        days = (datetime.now() - last_activity).days

        if days >= 14:
            inactive_users.append(f"{member.display_name} ({days}일)")

    if inactive_users:
        msg = "📢 역할 없는 14일 이상 미반응자\n\n"
        msg += "\n".join(inactive_users)
    else:
        msg = "📢 역할 없는 14일 이상 미반응자\n\n없음"

    await log_channel.send(msg)


async def send_reaction_ranking():
    guild = client.guilds[0]
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    data = load_data()
    ranking = []

    for user_id, info in data.items():
        member = guild.get_member(int(user_id))

        if not member:
            continue

        if isinstance(info, str):
            count = 0
        else:
            count = info.get("reaction_count", 0)

        ranking.append((member.display_name, count))

    ranking.sort(key=lambda x: x[1], reverse=True)

    current = datetime.now()
    target_month = current.month - 1
    target_year = current.year

    if target_month == 0:
        target_month = 12
        target_year -= 1

    msg = f"🏆 {target_year}년 {target_month}월 반응 TOP10\n\n"

    if ranking:
        for i, (name, count) in enumerate(ranking[:10], start=1):
            msg += f"{i}위 - {name} ({count}회)\n"
    else:
        msg += "기록 없음"

    await log_channel.send(msg)

    # 월간 카운트만 초기화, 마지막 반응 시간은 유지
    for user_id in data:
        if isinstance(data[user_id], dict):
            data[user_id]["reaction_count"] = 0

    save_data(data)


@client.event
async def on_ready():
    print(f"로그인 완료 : {client.user}")

    scheduler = AsyncIOScheduler()

    # 매일 00:00 미반응자 검사
    scheduler.add_job(
        check_inactive_users,
        "cron",
        hour=0,
        minute=0
    )

    # 매월 1일 00:01 월간 TOP10 출력
    scheduler.add_job(
        send_reaction_ranking,
        "cron",
        day=1,
        hour=0,
        minute=1
    )

    scheduler.start()


@client.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    save_activity(payload.user_id)

    guild = client.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if member is None:
        return

    await log_channel.send(
        f"✅ 반응 추가\n"
        f"사용자: {member.display_name}\n"
        f"이모지: {payload.emoji}"
    )


@client.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    guild = client.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if member is None:
        return

    await log_channel.send(
        f"❌ 반응 제거\n"
        f"사용자: {member.display_name}\n"
        f"이모지: {payload.emoji}"
    )


client.run(TOKEN)
