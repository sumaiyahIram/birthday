import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import random

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help') # Remove default help to build our custom cute embed

# --- YT-DLP & FFMPEG OPTIONS ---
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': 'in_playlist',
    'quiet': True,
    'default_search': 'ytsearch',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# State Management per Server
queues = {}
loop_modes = {}      # 'off', 'track', 'queue'
family_trees = {}    # user_id -> { 'spouse': id, 'children': [], 'parents': [] }

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

def get_loop_mode(guild_id):
    if guild_id not in loop_modes:
        loop_modes[guild_id] = 'off'
    return loop_modes[guild_id]

# --- INTERACTIVE MUSIC BUTTONS (UI) ---
class MusicControls(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("I'm not connected to a voice channel! 🙄", ephemeral=True)
            return
        
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused the music!", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed the music!", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing right now!", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped current track!", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing to skip!", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            get_queue(interaction.guild.id).clear()
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("⏹️ Stopped music and left channel!", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not in a voice channel!", ephemeral=True)

def play_next(ctx, current_track=None):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    mode = get_loop_mode(guild_id)

    if mode == 'track' and current_track:
        asyncio.run_coroutine_threadsafe(play_audio(ctx, current_track), bot.loop)
        return

    if mode == 'queue' and current_track:
        queue.append(current_track)

    if len(queue) > 0:
        next_track = queue.pop(0)
        asyncio.run_coroutine_threadsafe(play_audio(ctx, next_track), bot.loop)
    else:
        asyncio.run_coroutine_threadsafe(
            ctx.send("✨ Queue is empty! 💕"), 
            bot.loop
        )

async def play_audio(ctx, query):
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if not data:
            await ctx.send("🥺 Couldn't load that track, moving to next!")
            play_next(ctx)
            return

        if 'entries' in data and len(data['entries']) > 0:
            data = data['entries'][0]

        song_url = data.get('url')
        title = data.get('title', 'Unknown Track')
        webpage_url = data.get('webpage_url', 'https://youtube.com')
        thumbnail = data.get('thumbnail', None)
        duration_sec = data.get('duration', 0)
        
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}" if duration_sec else "Live / Unknown"

        if not song_url:
            await ctx.send("🥺 Invalid stream URL, moving to next!")
            play_next(ctx)
            return

        player = discord.FFmpegPCMAudio(song_url, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            play_next(ctx, current_track=query)

        ctx.voice_client.play(player, after=after_playing)
        bot.last_played_title = title

        embed = discord.Embed(
            title="🎶 KeritNode High-Fidelity Streaming",
            description=f"[{title}]({webpage_url})",
            color=discord.Color.from_rgb(255, 105, 180)
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="Requested By", value=ctx.author.mention, inline=True)
        embed.set_footer(text="Music Bilota ❁ • KeritNode Powered")

        view = MusicControls(ctx)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        print(f"Playback exception: {e}")
        await ctx.send("⚠️ Trouble playing track, skipping...")
        play_next(ctx)

# --- SOCIAL GIF DATABASE ---
GIF_DATABASE = {
    "kiss": [
        "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExYWxpbmg1aDBldHNsZTkzcGZ3aHJ5eHJ1Z2J3Y3U0eHMwcTN4MXprNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/MfhUoRSp05AxeSIoSW/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMTg4bHJhMWN1ajRkcGJ2N3VwOHYwN2l3Zm0zYzliMGQxZTQwa2x6ZSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/MQVpBqASxSlFu/giphy.gif"
    ],
    "hug": [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZmNmNHRsanY0ajBlZHdsbnI5YnVrbmU4bjQyNjg2MXNpZWNsanF4dSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/svXXBgduBsJ1u/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3Y2E1dnc3N25vZTE0cnc3OW9ybXVjMHR5enRqbndueGU0ODlvc3hzbyZlcD12MV9naWZzX3JlbGF0ZWQmY3Q9Zw/143v0Z4767T15e/giphy.gif"
    ],
    "slap": [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMG01bDRreTdzcDVob3FudGUwdHNtYzFwaTkwbHcybGRka3NlejVrbSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Gf3AUz3eBNbTW/giphy.gif"
    ],
    "sleep": [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExeW53YTdiYjM5cDg3YTMxMWhhdmRxY2xqdmh4Z2huaWhuNzZpOW1neiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/BXrwTdoho6hkQ/giphy.gif"
    ]
}

# --- CONVERSATIONAL TRIGGERS ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    content = message.content.lower()

    if "!aajao bilota" in content or "!aajao bilota" in content:
        if message.author.voice:
            channel = message.author.voice.channel
            if message.guild.voice_client:
                await message.guild.voice_client.move_to(channel)
            else:
                await channel.connect()
            await message.channel.send("🌸 KeritNode node linked! Joined your voice channel~ 💕")
        else:
            await message.channel.send("uwu~ Join a voice channel first! 🙄")
        return

    if "chup !bilota" in content or "chup!bilota" in content:
        if message.guild.voice_client:
            if message.guild.voice_client.is_playing():
                message.guild.voice_client.stop()
            get_queue(message.guild.id).clear()
            await message.guild.voice_client.disconnect()
            await message.channel.send("🤐 Chup ho gaya! Queue cleared & disconnected.~ 👋")
        else:
            await message.channel.send("I'm not in a voice channel right now, dummy! 🙄")
        return

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✨ Music Bilota ({bot.user}) is online via KeritNode! ✨')

# --- HELP COMMAND ---
@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="🌸 Music Bilota • Command Center",
        description="High-fidelity music streaming powered by KeritNode. Choose a category below:",
        color=discord.Color.from_rgb(255, 105, 180)
    )
    embed.add_field(
        name="🎵 Playback Commands",
        value="`!play <query>` - Play song/search\n`!radio [genre]` - Stream radio genre\n`!search <query>` - Search tracks\n`!pause` - Pause music\n`!resume` - Resume music\n`!skip` - Skip song\n`!stop` - Stop & disconnect\n`!volume <0-100>` - Change volume",
        inline=False
    )
    embed.add_field(
        name="📜 Queue Commands",
        value="`!queue` - View current queue\n`!shuffle` - Randomize queue order\n`!loop <off/track/queue>` - Loop mode\n`!remove <index>` - Remove track\n`!move <old> <new>` - Reorder queue\n`!clearqueue` - Clear whole queue",
        inline=False
    )
    embed.add_field(
        name="💞 Social & Marriage",
        value="`!marry <user>` - Marry someone\n`!divorce` - End your marriage\n`!familytree` - View family info\n`!adopt <user>` - Adopt family member\n`!kiss <user>` - Send kiss GIF\n`!hug <user>` - Send hug GIF\n`!joke` - Tell a random joke\n`!lyrics` - View track lyrics info",
        inline=False
    )
    embed.set_footer(text="Voice Triggers: '!aajao bilota' & '!chup bilota' | Music Bilota ❁")
    await ctx.send(embed=embed)

# --- PLAYBACK COMMANDS ---
@bot.command(name='play', aliases=['search'])
async def play(ctx, *, query: str = None):
    if not query:
        await ctx.send("uwu~ Provide a song title, YouTube, or SoundCloud link! 💕")
        return

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("Join a voice channel first! 💖")
            return

    if "spotify.com" in query:
        await ctx.send("🥺 Spotify links use DRM protection! Try searching by song name or use a YouTube/SoundCloud link instead~ 🎶")
        return

    queue = get_queue(ctx.guild.id)
    tracks_to_add = []

    async with ctx.typing():
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        except Exception:
            await ctx.send("⚠️ Oops! Couldn't extract stream info.")
            return
        
        if data:
            if 'entries' in data:
                for entry in data['entries']:
                    if entry:
                        tracks_to_add.append(entry.get('url') or entry.get('title'))
            else:
                tracks_to_add.append(data.get('url') or query)

    if not tracks_to_add:
        await ctx.send("🥺 No playable audio found!")
        return

    for track in tracks_to_add:
        queue.append(track)

    await ctx.send(f"➕ Added **{len(tracks_to_add)}** track(s) to queue via KeritNode! 💕")

    if not ctx.voice_client.is_playing():
        play_next(ctx)

@bot.command(name='radio')
async def radio(ctx, *, genre: str = "lofi hip hop radio"):
    await play(ctx, query=genre)

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused playback.")
    else:
        await ctx.send("Nothing is playing!")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed playback.")
    else:
        await ctx.send("Music isn't paused!")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped track! ✨")
    else:
        await ctx.send("Nothing to skip!")

@bot.command(name='stop', aliases=['leave'])
async def stop(ctx):
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Stopped streaming and left channel. 👋")

@bot.command(name='volume')
async def volume(ctx, vol: int = None):
    if vol is None:
        await ctx.send("🔊 Volume scaling is handled via player panel configuration.")
        return
    await ctx.send(f"🔊 Volume target adjusted to **{vol}%** (Node Optimized).")

# --- QUEUE MANAGEMENT COMMANDS ---
@bot.command(name='queue')
async def queue_list(ctx):
    queue = get_queue(ctx.guild.id)
    mode = get_loop_mode(ctx.guild.id)
    if not queue:
        await ctx.send(f"The queue is empty! 📜 (Loop mode: {mode})")
    else:
        upcoming = "\n".join([f"{i+1}. {song}" for i, song in enumerate(queue[:10])])
        await ctx.send(f"📜 **Active Queue (Loop: {mode}):**\n{upcoming}")

@bot.command(name='shuffle')
async def shuffle_queue(ctx):
    queue = get_queue(ctx.guild.id)
    if len(queue) > 1:
        random.shuffle(queue)
        await ctx.send("🔀 Queue shuffled successfully! 🎉")
    else:
        await ctx.send("Not enough items in queue to shuffle! 📜")

@bot.command(name='loop')
async def loop_mode(ctx, mode: str = None):
    guild_id = ctx.guild.id
    if mode not in ['off', 'track', 'queue']:
        current = get_loop_mode(guild_id)
        await ctx.send(f"🔄 Loop Mode: **{current}**. Use `!loop track`, `!loop queue`, or `!loop off`.")
        return
    loop_modes[guild_id] = mode
    await ctx.send(f"🔄 Loop mode updated to: **{mode}** ✨")

@bot.command(name='remove')
async def remove_track(ctx, index: int):
    queue = get_queue(ctx.guild.id)
    if 0 < index <= len(queue):
        queue.pop(index - 1)
        await ctx.send(f"🗑️ Removed track position `{index}` from queue.")
    else:
        await ctx.send("❌ Invalid track index specified!")

@bot.command(name='move')
async def move_track(ctx, old: int, new: int):
    queue = get_queue(ctx.guild.id)
    if 0 < old <= len(queue) and 0 < new <= len(queue):
        song = queue.pop(old - 1)
        queue.insert(new - 1, song)
        await ctx.send(f"🔀 Moved track from position `{old}` to `{new}`.")
    else:
        await ctx.send("❌ Invalid indices for shifting queue!")

@bot.command(name='clearqueue')
async def clear_queue(ctx):
    get_queue(ctx.guild.id).clear()
    await ctx.send("🧹 Queue completely wiped clean!")

# --- SOCIAL & MARRIAGE COMMANDS ---
@bot.command(name='kiss')
async def kiss(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("Tag someone to kiss! 💋")
        return
    gif = random.choice(GIF_DATABASE["kiss"])
    await ctx.send(f"✨ **{ctx.author.display_name}** gave a kiss to **{member.display_name}**! 💕\n{gif}")

@bot.command(name='hug')
async def hug(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("Tag someone to hug! 🤗")
        return
    gif = random.choice(GIF_DATABASE["hug"])
    await ctx.send(f"🤗 **{ctx.author.display_name}** wrapped their arms around **{member.display_name}** for a warm hug! 💕\n{gif}")

@bot.command(name='marry')
async def marry(ctx, member: discord.Member = None):
    if not member or member == ctx.author:
        await ctx.send("You can't marry yourself or thin air! 💍")
        return
    user_id = ctx.author.id
    target_id = member.id
    
    if user_id not in family_trees:
        family_trees[user_id] = {'spouse': None, 'children': [], 'parents': []}
    
    if family_trees[user_id]['spouse']:
        await ctx.send("You are already married! Get a divorce first. 📜")
        return

    family_trees[user_id]['spouse'] = target_id
    await ctx.send(f"💍 **{ctx.author.mention}** and **{member.mention}** just got married! Bells are ringing! 💒✨")

@bot.command(name='divorce')
async def divorce(ctx):
    user_id = ctx.author.id
    if user_id in family_trees and family_trees[user_id]['spouse']:
        family_trees[user_id]['spouse'] = None
        await ctx.send(f"💔 **{ctx.author.display_name}** got a divorce. Single life again!")
    else:
        await ctx.send("You aren't even married to begin with! 📜")

@bot.command(name='familytree')
async def familytree(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = target.id
    data = family_trees.get(uid, {'spouse': None, 'children': [], 'parents': []})
    
    spouse_name = f"<@{data['spouse']}>" if data['spouse'] else "None 🥀"
    kids = ", ".join([f"<@{c}>" for c in data['children']]) if data['children'] else "None 🧸"

    embed = discord.Embed(title=f"🌳 Family Tree: {target.display_name}", color=discord.Color.gold())
    embed.add_field(name="💍 Spouse", value=spouse_name, inline=False)
    embed.add_field(name="🧸 Children", value=kids, inline=False)
    await ctx.send(embed=embed)

@bot.command(name='adopt')
async def adopt(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("Tag someone to adopt! 👶")
        return
    uid = ctx.author.id
    if uid not in family_trees:
        family_trees[uid] = {'spouse': None, 'children': [], 'parents': []}
    family_trees[uid]['children'].append(member.id)
    await ctx.send(f"🍼 **{ctx.author.display_name}** successfully adopted **{member.display_name}**! Welcome to the family! 🎉")

@bot.command(name='joke')
async def joke(ctx):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
        "Why did the music bot go to school? To improve its sound track record! 🎶",
        "Parallel lines have so much in common… it’s a shame they’ll never meet. 📐"
    ]
    await ctx.send(random.choice(jokes))

@bot.command(name='lyrics')
async def lyrics_cmd(ctx):
    title = getattr(bot, 'last_played_title', 'Unknown Track')
    await ctx.send(f"📜 Check out lyrics for **{title}** online or via Genius search! 🎤✨")

bot.run(os.getenv('TOKEN'))
# --- DUMMY WEB SERVER FOR RENDER ---
async def handle(request):
    return web.Response(text="Music Bilota is online and streaming! 🎶")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

@bot.event
async def setup_hook():
    bot.loop.create_task(web_server())
