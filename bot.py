
import discord
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# =====================================
# 기본 설정
# =====================================

TOKEN = os.getenv("TOKEN")

TARGET_CHANNEL_ID = 1375102819673313380
LOG_CHANNEL_ID = 1515550120727543919

# 한국 시간대
KST = ZoneInfo("Asia/Seoul")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.reactions = True

client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler(timezone=KST)


# =====================================
# 시간 관련 함수
# =====================================

def now_kst():
    return datetime.now(KST)


def parse_datetime(value):
    """기존 데이터와 새 시간 데이터를 모두 처리합니다."""
    dt = datetime.fromisoformat(value)

    # 기존에 저장된 시간대 없는 데이터는 한국 시간으로 간주
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)

    return dt.astimezone(KST)


# =====================================
# JSON 데이터 관리
# =====================================

def load_data():
    try:
        with open("user_activity.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("user_activity.json 파일의 형식이 올바르지 않습니다.")
        return {}


def save_data(data):
    with open("user_activity.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# =====================================
# 게시글 링크 생성
# =====================================

def create_message_url(guild_id, channel_id, message_id):
    return (
        f"https://discord.com/channels/"
        f"{guild_id}/{channel_id}/{message_id}"
    )


# =====================================
# 긴 메시지 나누어 전송
# =====================================

async def send_long_message(channel, message):
    """디스코드 메시지 길이 제한에 맞춰 나누어 보냅니다."""
    max_length = 1900
    parts = []
    current = ""

    for line in message.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                parts.append(current)
            current = line
        else:
            if current:
                current += "\n" + line
            else:
                current = line

    if current:
        parts.append(current)

    for part in parts:
        await channel.send(part)


# =====================================
# 반응 활동 저장
# =====================================

def save_activity(user_id, guild_id, channel_id, message_id, emoji):
    data = load_data()
    user_id = str(user_id)

    now = now_kst().isoformat()

    message_url = create_message_url(
        guild_id,
        channel_id,
        message_id
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
        if isinstance(data[user_id], str):
            old_activity = data[user_id]
            data[user_id] = {
                "last_activity": old_activity,
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


# =====================================
# 미반응자 확인
# =====================================

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

    # 12~13일 미반응자
    inactive_12_users = []

    # 14일 이상 미반응자
    inactive_14_users = []

    current_time = now_kst()

    for member in guild.members:
        # 봇 제외
        if member.bot:
            continue

        # @everyone 역할만 가진 사람만 확인
        if len(member.roles) > 1:
            continue

        user_id = str(member.id)

        # 반응 기록이 없는 사람 제외
        if user_id not in data:
            continue

        user_data = data[user_id]

        # 예전 형식의 데이터도 처리
        if isinstance(user_data, str):
            last_activity = parse_datetime(user_data)
            last_emoji = "기록 없음"
            last_message_url = "기록 없음"
        else:
            if "last_activity" not in user_data:
                continue

            last_activity = parse_datetime(
                user_data["last_activity"]
            )

            last_emoji = user_data.get(
                "last_emoji",
                "기록 없음"
            )

            last_message_url = user_data.get(
                "last_message_url",
                "기록 없음"
            )

        days = (current_time - last_activity).days

        user_info = (
            f"{member.display_name} ({days}일)\n"
            f"마지막 이모지: {last_emoji}\n"
            f"마지막으로 반응한 글: {last_message_url}\n"
        )

        # 12~13일 미반응
        if 12 <= days < 14:
            inactive_12_users.append(user_info)

        # 14일 이상 미반응
        elif days >= 14:
            inactive_14_users.append(user_info)

    # 12~13일 미반응자 메시지
    if inactive_12_users:
        msg_12 = (
            "📢 역할 없는 12일 이상 미반응자\n\n"
            + "\n".join(inactive_12_users)
        )
    else:
        msg_12 = (
            "📢 역할 없는 12일 이상 미반응자\n\n"
            "없음"
        )

    await send_long_message(log_channel, msg_12)

    # 14일 이상 미반응자 메시지
    if inactive_14_users:
        msg_14 = (
            "📢 역할 없는 14일 이상 미반응자\n\n"
            + "\n".join(inactive_14_users)
        )
    else:
        msg_14 = (
            "📢 역할 없는 14일 이상 미반응자\n\n"
            "없음"
        )

    await send_long_message(log_channel, msg_14)

    print("미반응자 확인 완료")


# =====================================
# 월간 반응 TOP 10
# =====================================

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

    # 지난달 연도와 월 계산
    current = now_kst()
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

    await send_long_message(log_channel, msg)

    # 반응 횟수 초기화
    for user_id in data:
        if isinstance(data[user_id], dict):
            data[user_id]["reaction_count"] = 0

    save_data(data)

    print("월간 반응 순위 전송 및 초기화 완료")


# =====================================
# 봇 실행 준비
# =====================================

@client.event
async def on_ready():

    print(f"로그인 완료 : {client.user}")

    if not scheduler.running:

        scheduler.add_job(
            check_inactive_users,
            "cron",
            hour=0,
            minute=0,
            id="check_inactive_users",
            replace_existing=True
        )

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

        print("스케줄러 시작 완료")


# =====================================
# 반응 추가 테스트
# =====================================

@client.event
async def on_raw_reaction_add(payload):

    print(
        f"🔔 반응 감지됨 "
        f"channel={payload.channel_id}, "
        f"message={payload.message_id}, "
        f"user={payload.user_id}"
    )

    # 감시 채널인지 확인
    if payload.channel_id != TARGET_CHANNEL_ID:

        print(
            f"❌ 다른 채널의 반응입니다. "
            f"현재={payload.channel_id}, "
            f"설정={TARGET_CHANNEL_ID}"
        )

        return

    print("✅ 감시 채널의 반응입니다.")

    if payload.guild_id is None:

        print("❌ 서버 반응이 아닙니다.")

        return

    guild = client.get_guild(
        payload.guild_id
    )

    if guild is None:

        print(
            "❌ 서버를 찾을 수 없습니다."
        )

        return

    member = guild.get_member(
        payload.user_id
    )

    if member is None:

        print(
            "❌ 사용자를 찾을 수 없습니다."
        )

        return

    if member.bot:

        print(
            "❌ 봇의 반응입니다."
        )

        return

    log_channel = client.get_channel(
        LOG_CHANNEL_ID
    )

    if log_channel is None:

        print(
            "❌ 로그 채널을 찾을 수 없습니다."
        )

        return

    print(
        f"✅ 사용자 확인 완료: "
        f"{member.display_name}"
    )

    # =================================
    # 활동 기록 저장
    # =================================

    save_activity(

        payload.user_id,

        payload.guild_id,

        payload.channel_id,

        payload.message_id,

        payload.emoji
    )

    # =================================
    # 게시글 링크
    # =================================

    message_url = create_message_url(

        payload.guild_id,

        payload.channel_id,

        payload.message_id
    )

    # =================================
    # 로그 전송
    # =================================

    await send_long_message(

        log_channel,

        (
            "✅ 반응 추가\n"

            f"사용자: "
            f"{member.display_name}\n"

            f"이모지: "
            f"{payload.emoji}\n"

            f"게시글: "
            f"{message_url}"
        )
    )

    print(
        "✅ 반응 로그 전송 완료"
    )
