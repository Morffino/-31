import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import asyncio
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация из переменных окружения
TOKEN = os.getenv('MTUyOTk5OTQyNjE5MjQwODgyNg.Gfm_vQ.nFRqrP-4Uj-gsRMVatrd_EwFq9YgWbAC6W31Xo')
GUILD_ID = int(os.getenv('GUILD_ID', 0))
CATEGORY_ID = int(os.getenv('CATEGORY_ID', 0))
STAFF_ROLE_ID = int(os.getenv('STAFF_ROLE_ID', 0))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0))
TICKET_LIFETIME_HOURS = int(os.getenv('TICKET_LIFETIME_HOURS', 10))

# Проверка конфигурации
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле!")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище активных тикетов
tickets = {}
ticket_history = {}

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Общие вопросы", style=discord.ButtonStyle.primary, custom_id="general")
    async def general_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Общие вопросы")
    
    @discord.ui.button(label="Восстановление вещей", style=discord.ButtonStyle.success, custom_id="restore")
    async def restore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Восстановление вещей")
    
    @discord.ui.button(label="Технические проблемы", style=discord.ButtonStyle.warning, custom_id="tech")
    async def tech_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Технические проблемы")
    
    @discord.ui.button(label="Жалоба на игрока", style=discord.ButtonStyle.danger, custom_id="player_report")
    async def player_report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на игрока/группировку")
    
    @discord.ui.button(label="Жалоба на Администрацию", style=discord.ButtonStyle.danger, custom_id="admin_report")
    async def admin_report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на Администрацию")
    
    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        # Проверка на существующий тикет
        for ticket in tickets.values():
            if ticket['user_id'] == interaction.user.id and ticket['status'] == 'open':
                await interaction.response.send_message("У вас уже есть открытый тикет!", ephemeral=True)
                return
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("Категория для тикетов не найдена!", ephemeral=True)
            return
        
        ticket_number = len([t for t in tickets.values() if t['status'] == 'open']) + 1
        channel_name = f"ticket-{interaction.user.name.lower()}-{ticket_number}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {interaction.user.name} - {topic}"
        )
        
        tickets[channel.id] = {
            'user_id': interaction.user.id,
            'user_name': interaction.user.name,
            'topic': topic,
            'status': 'open',
            'created_at': datetime.now().isoformat(),
            'closing_time': (datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)).isoformat(),
            'messages': [],
            'staff_members': []
        }
        
        embed = discord.Embed(
            title="HS TICKET | Центр поддержки",
            description=f"Тикет создан по теме: **{topic}**",
            color=0x00ff00
        )
        embed.add_field(name="Укажите ваш SteamID64", value="Можно узнать тут: https://steamid.io", inline=False)
        embed.add_field(name="Ваш ник в игре", value="Укажите игровой ник", inline=False)
        embed.add_field(name="Кратко о проблеме", value="До 30 символов", inline=False)
        embed.add_field(
            name="⏰ Время до автоматического закрытия",
            value=f"Тикет будет автоматически закрыт через {TICKET_LIFETIME_HOURS} часов",
            inline=False
        )
        embed.set_footer(text=f"Тикет создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        view = TicketControlView()
        await channel.send(f"{interaction.user.mention} {guild.get_role(STAFF_ROLE_ID).mention}", embed=embed, view=view)
        
        bot.loop.create_task(auto_close_ticket(channel.id))
        
        # Логирование
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📩 Создан новый тикет",
                description=f"Пользователь: {interaction.user.mention}\nТема: {topic}\nКанал: {channel.mention}",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            await log_channel.send(embed=log_embed)
        
        await interaction.response.send_message(f"Тикет создан! Перейдите в канал {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для закрытия тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        await close_ticket(channel, interaction.user, "Закрыт по запросу персонала")
        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...")
    
    @discord.ui.button(label="Продлить тикет", style=discord.ButtonStyle.primary, custom_id="extend_ticket")
    async def extend_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для продления тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        tickets[channel.id]['closing_time'] = (datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)).isoformat()
        
        embed = discord.Embed(
            title="⏰ Тикет продлен",
            description=f"Тикет продлен на {TICKET_LIFETIME_HOURS} часов.",
            color=0x00ff00
        )
        await channel.send(embed=embed)
        await interaction.response.send_message("Тикет успешно продлен!", ephemeral=True)

async def auto_close_ticket(channel_id):
    await asyncio.sleep(TICKET_LIFETIME_HOURS * 3600)
    
    if channel_id not in tickets or tickets[channel_id]['status'] != 'open':
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    embed = discord.Embed(
        title="⏰ Автоматическое закрытие",
        description=f"Тикет будет закрыт через 60 секунд.",
        color=0xff0000
    )
    await channel.send(embed=embed)
    await asyncio.sleep(60)
    
    if channel_id not in tickets or tickets[channel_id]['status'] != 'open':
        return
    
    await close_ticket(channel, bot.user, "Автоматическое закрытие по истечении времени")

async def close_ticket(channel, closer, reason):
    if channel.id not in tickets:
        return
    
    ticket_info = tickets[channel.id]
    
    # Собираем сообщения для лога
    messages = []
    async for msg in channel.history(limit=200, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content[:100]}")
    
    # Логирование в канал
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="📪 Тикет закрыт",
            description=f"**Создатель:** {ticket_info['user_name']}\n**Тема:** {ticket_info['topic']}\n**Закрыл:** {closer.name if hasattr(closer, 'name') else 'Auto'}\n**Причина:** {reason}",
            color=0xff0000,
            timestamp=datetime.now()
        )
        await log_channel.send(embed=embed)
        
        # Сохраняем лог в файл
        log_text = f"=== ЛОГ ТИКЕТА ===\nID: {channel.id}\nСоздан: {ticket_info['created_at']}\nЗакрыт: {datetime.now().isoformat()}\nПользователь: {ticket_info['user_name']}\nТема: {ticket_info['topic']}\n========================\n\n"
        log_text += "\n".join(messages)
        
        filename = f"ticket_log_{channel.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(log_text)
        
        await log_channel.send(file=discord.File(filename))
        os.remove(filename)
    
    del tickets[channel.id]
    await channel.delete()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')
    print(f'📊 На сервере: {len(bot.guilds)} гильдий')
    
    # Создание основного сообщения с тикетами
    guild = bot.get_guild(GUILD_ID)
    if guild:
        ticket_channel = discord.utils.get(guild.text_channels, name="tickets")
        if ticket_channel:
            # Очищаем старые сообщения
            async for message in ticket_channel.history(limit=100):
                if message.author == bot.user:
                    await message.delete()
            
            embed = discord.Embed(
                title="Добро пожаловать",
                description="Это начало канала #кикеты.",
                color=0x3498db
            )
            embed.add_field(
                name="HS HELPER [БОТ]",
                value=f"**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n⏰ **Тикеты автоматически закрываются через {TICKET_LIFETIME_HOURS} часов**",
                inline=False
            )
            
            view = TicketView()
            await ticket_channel.send(embed=embed, view=view)
            print('✅ Основное сообщение создано!')

@bot.command(name='setup')
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    """Настройка системы тикетов"""
    embed = discord.Embed(
        title="Добро пожаловать",
        description="Это начало канала #кикеты.",
        color=0x3498db
    )
    embed.add_field(
        name="HS HELPER [БОТ]",
        value=f"**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n⏰ **Тикеты автоматически закрываются через {TICKET_LIFETIME_HOURS} часов**",
        inline=False
    )
    
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

if __name__ == '__main__':
    bot.run(TOKEN)
