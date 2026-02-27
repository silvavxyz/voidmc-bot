import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import asyncio
from datetime import datetime
import io

# ════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO — edite aqui
# ════════════════════════════════════════════════════════════════════

TOKEN = "SEU_TOKEN_AQUI"
STAFF_ROLE_ID = 1471367686448615567
LOG_CHANNEL_ID = 0        # ID do canal de logs — troque pelo seu
TICKET_CATEGORY_ID = 0    # ID da categoria onde os tickets serão criados — troque pelo seu

# ════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

CATEGORIAS = {
    "suporte":   {"emoji": "🛠️", "label": "Suporte",    "cor": discord.Color.blue()},
    "compra":    {"emoji": "🛒", "label": "Compra",     "cor": discord.Color.green()},
    "denuncia":  {"emoji": "🔨", "label": "Denúncia",   "cor": discord.Color.red()},
    "parceria":  {"emoji": "📢", "label": "Parceria",   "cor": discord.Color.purple()},
}


# ════════════════════════════════════════════════════════════════════
# VIEW — Botões de abertura de ticket
# ════════════════════════════════════════════════════════════════════

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, val in CATEGORIAS.items():
            btn = Button(
                label=val["label"],
                emoji=val["emoji"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket_{key}"
            )
            btn.callback = self.make_callback(key)
            self.add_item(btn)

    def make_callback(self, categoria):
        async def callback(interaction: discord.Interaction):
            await abrir_ticket(interaction, categoria)
        return callback


# ════════════════════════════════════════════════════════════════════
# VIEW — Botão de fechar ticket
# ════════════════════════════════════════════════════════════════════

class FecharView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar Ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="fechar_ticket")
    async def fechar(self, interaction: discord.Interaction, button: Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        eh_staff = staff_role in interaction.user.roles
        eh_dono = interaction.channel.topic and str(interaction.user.id) in interaction.channel.topic

        if not eh_staff and not eh_dono:
            await interaction.response.send_message("❌ Você não tem permissão para fechar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Fechando ticket e salvando transcript...")
        await fechar_ticket(interaction.channel, interaction.guild, interaction.user)


# ════════════════════════════════════════════════════════════════════
# FUNÇÕES
# ════════════════════════════════════════════════════════════════════

async def abrir_ticket(interaction: discord.Interaction, categoria: str):
    guild = interaction.guild
    user = interaction.user
    info = CATEGORIAS[categoria]

    # Verifica se já tem ticket aberto
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic and categoria in channel.name:
            await interaction.response.send_message(
                f"❌ Você já tem um ticket de **{info['label']}** aberto: {channel.mention}",
                ephemeral=True
            )
            return

    staff_role = guild.get_role(STAFF_ROLE_ID)
    category_obj = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        staff_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    canal_nome = f"{info['emoji']}-{categoria}-{user.name}".lower().replace(" ", "-")
    channel = await guild.create_text_channel(
        name=canal_nome,
        overwrites=overwrites,
        category=category_obj,
        topic=f"Ticket de {user.id} | Categoria: {categoria}"
    )

    embed = discord.Embed(
        title=f"{info['emoji']} Ticket de {info['label']}",
        description=(
            f"Olá, {user.mention}! 👋\n\n"
            f"Seu ticket de **{info['label']}** foi aberto com sucesso.\n"
            f"Descreva sua situação com o máximo de detalhes possível e aguarde — nossa equipe logo te atenderá!\n\n"
            f"⚠️ Não feche o ticket antes de ser atendido."
        ),
        color=info["cor"],
        timestamp=datetime.now()
    )
    embed.set_footer(text="Void MC • Suporte")

    await channel.send(content=f"{user.mention} | {staff_role.mention}", embed=embed, view=FecharView())
    await interaction.response.send_message(f"✅ Ticket aberto! {channel.mention}", ephemeral=True)

    # Log de abertura
    await enviar_log(guild, "aberto", user, channel, categoria)


async def fechar_ticket(channel: discord.TextChannel, guild: discord.Guild, fechado_por: discord.User):
    # Gera transcript
    mensagens = []
    async for msg in channel.history(limit=500, oldest_first=True):
        hora = msg.created_at.strftime("%d/%m/%Y %H:%M")
        mensagens.append(f"[{hora}] {msg.author.display_name}: {msg.content}")

    transcript_texto = "\n".join(mensagens) if mensagens else "Nenhuma mensagem."
    transcript_bytes = transcript_texto.encode("utf-8")
    arquivo = discord.File(io.BytesIO(transcript_bytes), filename=f"transcript-{channel.name}.txt")

    # Envia transcript pro log
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="🔒 Ticket Fechado",
            description=(
                f"**Canal:** {channel.name}\n"
                f"**Fechado por:** {fechado_por.mention}\n"
                f"**Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            ),
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.set_footer(text="Void MC • Logs")
        await log_channel.send(embed=embed, file=arquivo)

    await asyncio.sleep(3)
    await channel.delete()


async def enviar_log(guild, tipo, user, channel, categoria):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    info = CATEGORIAS[categoria]
    cor = discord.Color.green() if tipo == "aberto" else discord.Color.red()
    titulo = "📂 Ticket Aberto" if tipo == "aberto" else "🔒 Ticket Fechado"

    embed = discord.Embed(
        title=titulo,
        description=(
            f"**Usuário:** {user.mention}\n"
            f"**Categoria:** {info['emoji']} {info['label']}\n"
            f"**Canal:** {channel.mention}\n"
            f"**Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ),
        color=cor,
        timestamp=datetime.now()
    )
    embed.set_footer(text="Void MC • Logs")
    await log_channel.send(embed=embed)


# ════════════════════════════════════════════════════════════════════
# COMANDO — /setup (envia o painel de tickets)
# ════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setup", description="Envia o painel de tickets no canal atual")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚔️ Suporte — Void MC",
        description=(
            "Precisa de ajuda? Selecione abaixo a categoria do seu ticket "
            "e nossa equipe te atenderá o mais rápido possível!\n\n"
            "🛠️ **Suporte** — Problemas técnicos, bugs, itens\n"
            "🛒 **Compra** — VIPs e benefícios\n"
            "🔨 **Denúncia** — Reporte de jogadores (tenha provas!)\n"
            "📢 **Parceria** — Propostas de parceria e divulgação\n\n"
            "⚠️ Não abra tickets sem necessidade."
        ),
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    embed.set_footer(text="Void MC • Suporte")
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)


# ════════════════════════════════════════════════════════════════════
# EVENTOS
# ════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(FecharView())
    await bot.tree.sync()
    print(f"[Void MC] Bot online como {bot.user}")


bot.run(TOKEN)
