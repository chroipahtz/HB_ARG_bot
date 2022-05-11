from disnake.ext import commands
from disnake import Interaction
import disnake
import aiohttp
import asyncio
import orjson
import hashlib
import io
import os
import re
import datetime
from lxml import html
from urllib.parse import urlparse, unquote
from enum import Enum

# clean text from html tags


def clean_text(string):
    string = string.replace("</h2><p>", "**\n\n")
    string = string.replace("<br>", "\n")
    string = string.replace("</p>", "")
    string = string.replace("<h2>", "**")
    return string


class ARG(commands.Cog, name="ARG"):
    """ARG related functions"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.setup_bats_parser()
        self.setup_monitoring()
        self.setup_discord_channels()
        self.setup_pair_info()

        asyncio.ensure_future(self.monitor_bats())

    # setup functions

    def setup_bats_parser(self):
        # maybe we could try getting the key automatically from the document, or read it from a file
        self.decryptkey = {
            "yellowsnake": "I", "orangeturtle": "23", "whitedog": "6", "yellowmouse": "15", "redcat": "↗", "reddog": "51", "whiteelephant": ".-", "orangesnake": "J", "orangegiraffe": "H", "🙁": "T", "sadface": "T", "yellowelephant": "2", "bluepenguin": "U", "bluegiraffe": "F", "redmouse": "S", "bluerabbit": "H", "yellowcat": "O", "bluedog": "E", "redrabbit": "S", "blackdog": "E", "yellowrabbit": "R", "greenfrog": "←", "greenowl": "E", "👁️": "U", "eye": "U", "yellowbat": "P", "whiteturtle": "A", "bluecat": "I", "blackpenguin": "R", "whiteowl": "C", "blackturtle": "3", "redpenguin": "S", "bluesnake": "P", "redelephant": "K", "greengiraffe": "L", "blackrabbit": "M", "greenbat": "21", "upsidedownface": "L", "whitecat": "T", "whitebat": "L", "orangedog": "E", "greenelephant": "T", "yellowpenguin": "A", "orangefrog": "F", "blackcat": "M", "yellowdog": "...", "whitegiraffe": "N", "redfrog": "4", "whitepenguin": "♡", "yellowturtle": "Y", "yellowowl": "53", "💀": "A", "skull": "A", "orangeowl": "T", "redgiraffe": "111", "bluemouse": "-.-.", "greensnake": "↖", "blackfrog": "ZYXWVUTSRQPONMLKJIHGFEDCBA", "redowl": "→", "greenturtle": "R", "orangecat": "A", "🙂": "M", "happyface": "M", "orangeelephant": "N", "blacksnake": ".--.", "blueturtle": "♅", "orangebat": "1", "whitefrog": "41", "greenmouse": "C", "blackgiraffe": "5", "blackmouse": "↘", "greenrabbit": "4", "blueelephant": "A"
        }
        self.encryptkey = {y: x for x, y in self.decryptkey.items()}

    def setup_monitoring(self):
        self.bats_url = "https://sunaiku-foundation.com/en/hiddenbats/"
        self.filename = "hiddenbats"
        self.nonce = None

    def setup_discord_channels(self):
        self.admins = orjson.loads(os.getenv('DISCORD_ADMINS', '[]'))
        self.monitor_channels = orjson.loads(
            os.getenv('DISCORD_MONITOR_CHANNELS', '[]'))
        self.command_channels = orjson.loads(
            os.getenv('DISCORD_COMMAND_CHANNELS', '[]'))
    
    def setup_pair_info(self):
        self.pair_names = orjson.loads(
            os.getenv('PAIR_INFO', '[]')
        )
        self.first_tweet_date = orjson.loads(
            os.getenv('PAIR_FIRST_TWEET_DATE', '[]')
        )

    # helper functions

    class Language(str, Enum):
        English = 'en'
        Japanese = 'jp'

    # functions for bats489 decryption and encryption. thanks to salty-dracon#8328 for the original code!

    def bats_decrypt(self, inputstring):
        splitlist = inputstring.split(" ")
        combilist = []
        for i in range(len(splitlist)):
            if splitlist[i].lower() in self.decryptkey:
                combilist.append(self.decryptkey[splitlist[i].lower()])
        bit = ""
        joinedlist = bit.join(combilist)
        if len(joinedlist) == 0:
            return "No valid characters found."
        else:
            return joinedlist

    def bats_encrypt(self, inputstring):
        combilist = []
        for i in range(len(inputstring)):
            if inputstring[i].upper() in self.encryptkey:
                combilist.append(self.encryptkey[inputstring[i].upper()])
                combilist.append(" ")
        bit = ""
        joinedlist = bit.join(combilist)
        if len(joinedlist) == 0:
            return "No valid characters found."
        else:
            return joinedlist

    async def get_bats(self, session):
        async with session.get(self.bats_url) as r:
            if r.status == 200:
                data = await r.read()
                return data

    def is_not_in_whitelist(self, channel_id):
        return not channel_id in self.command_channels

    def response_to_byte_array(self, response_data):
        arr = io.BytesIO()
        arr.write(response_data)
        arr.seek(0)
        return arr

    def get_nonce(self, response):
        tree = html.fromstring(response)
        script = tree.xpath('/html/body/script[5]')[0].text
        try:
            return re.search("(?<='nonce': ')(.*)(?=',)", script)[0]
        except(TypeError):
            print('No nonce found.')
            return None

    # events

    @commands.Cog.listener()
    async def on_message(self, message):
        
        if message.author == self.bot.user:
            return

        # make these better later
        if isinstance(message.channel, disnake.TextChannel):
            
            if message.author.nick == "Aine Ichirai/壱来アイネ":
                if message.content.find('https://twitter.com/Aine_Ichirai/status/') != -1:
                    await message.reply('<:MizukiThumbsUp:925566710243803156>')
                    return

            if message.author.nick == "Binato Sotobara/卒斗原ビナト":
                if message.content.find('https://twitter.com/Binato_Sotobara/status/') != -1:
                    await message.reply('<:MizukiThumbsUp:925566710243803156>')
                    return

    # monitors hiddenbats site for any changes

    async def monitor_bats(self):
        response = ""
        prevHash = ""
        prevResponse = ""
        await self.bot.wait_until_ready()
        print('Starting bats monitoring.')
        channels = [self.bot.get_channel(channel)
                    for channel in self.monitor_channels]
        # check if bot can actually access all monitor channels
        if None in channels:
            print('Failed to get info for a channel, retrying.')
            await asyncio.sleep(10)  # wait 10 seconds before trying again
            channels = [self.bot.get_channel(channel)
                        for channel in self.monitor_channels]
            if None in channels:
                print('Failed to get info for a channel.')
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # perform the get request and store it in a var
                    response = await self.get_bats(session)
                    currentHash = hashlib.sha1(response).hexdigest()
                    # check if new hash is same as the previous hash
                    if prevHash != currentHash:
                        if len(prevHash) != 0:
                            prev_nonce = self.nonce
                            prev_file = disnake.File(self.response_to_byte_array(
                                prevResponse), filename=f'{self.filename}_old.html')
                            current_file = disnake.File(self.response_to_byte_array(
                                response), filename=f'{self.filename}_new.html')
                            self.nonce = self.get_nonce(response)
                            # notify about changes
                            if prev_nonce != self.nonce:
                                for channel in channels:
                                    async with channel.typing():
                                        await channel.send(f'Something changed in hiddenbats site <:MizukiThumbsUp:925566710243803156>.\nPrevious nonce: {prev_nonce}\nPrevious HTML:', file=prev_file)
                                        await channel.send(f'New nonce: {self.nonce}\nNew HTML:', file=current_file)
                            else:
                                for channel in channels:
                                    async with channel.typing():
                                        await channel.send(f'Something changed in hiddenbats site <:MizukiThumbsUp:925566710243803156>.\nPrevious HTML:', file=prev_file)
                                        await channel.send(f'New HTML:', file=current_file)
                        else:
                            self.nonce = self.get_nonce(response)
                        prevHash = currentHash
                        prevResponse = response
                    # wait for 30 seconds
                    await asyncio.sleep(30)
                # handle exceptions
                except Exception as e:
                    print("Error", e)
                    for channel in channels:
                        channel.send(
                            'An error happened, please report it to the bot creator kthx:', e)

    # slash commands

    @commands.slash_command(
        name="password", description="Tries the password on the hiddenbats site."
    )
    async def password(self, interaction=Interaction, *, password: str, language: Language = 'en'):
        if self.nonce == None:
            await interaction.response.send_message("Nonce is missing. Please wait a bit or contact the bot's creator if this persists.")
            return
        form_data = aiohttp.FormData()
        form_data.add_field("action", "hiddenbats_password_check")
        form_data.add_field("nonce", self.nonce)
        form_data.add_field("password", password)
        if language == 'jp':
            url = "https://sunaiku-foundation.com/wp-admin/admin-ajax.php"
        else:
            url = "https://sunaiku-foundation.com/en/wp-admin/admin-ajax.php"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data) as r:
                if r.status == 200:
                    data = await r.text()
                    text = orjson.loads(data)
                    if text["state"] == "correct":
                        await interaction.response.send_message(clean_text(text["html"]), ephemeral=self.is_not_in_whitelist(interaction.channel_id))
                    elif text["state"] == "failed":
                        await interaction.response.send_message('Wrong password.', ephemeral=self.is_not_in_whitelist(interaction.channel_id))
                    else:
                        await interaction.response.send_message(f'Unknown state {text["state"]}.', ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        return

    @commands.slash_command(
        name="decrypt", description="Decrypts a bats489 encrypted string."
    )
    async def decrypt(self, interaction=Interaction, *, string):
        await interaction.response.send_message(self.bats_decrypt(string), ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        return

    @commands.slash_command(
        name="thumbsup", description="you have 21 minutes to get help"
    )
    async def thumbsup(self, interaction=Interaction):
        await interaction.response.send_message("<:MizukiThumbsUp:925566710243803156>", ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        return

    # TODO - handle strings longer than 2000 characters, maybe upload as a file?
    @commands.slash_command(
        name="encrypt", description="Encrypts a string with bats489."
    )
    async def encrypt(self, interaction=Interaction, *, string):
        await interaction.response.send_message(self.bats_encrypt(string), ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        return

    @commands.slash_command(
        name="media", description="Mirrors the specified picture/video from the Sunaiku Foundation website."
    )
    async def media(self, interaction=Interaction, *, url):
        if not url.startswith("https://sunaiku-foundation.com"):
            await interaction.response.send_message("Not a valid Sunaiku Foundation URL.", ephemeral=True)
            return
        filename = os.path.basename(unquote(urlparse(url).path))
        _, extension = os.path.splitext(filename)
        if not extension in [".png", ".jpg", ".jpeg", ".webm", ".mp4"]:
            await interaction.response.send_message("Not a valid picture/video URL.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'referer': 'https://sunaiku-foundation.com/'}) as resp:
                buffer = io.BytesIO(await resp.read())
        if resp.status == 200:
            await interaction.followup.send(file=disnake.File(buffer, filename=filename), ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        elif resp.status == 403:
            await interaction.followup.send("Unauthorized, cannot access image.", ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        elif resp.status == 404:
            await interaction.followup.send("Image not found.", ephemeral=self.is_not_in_whitelist(interaction.channel_id))
        else:
            await interaction.followup.send(f"Failed. Unknown response code: {resp.status}. Please contact the bot's creator kthx.")
        return

    @commands.slash_command(
        name="time", description="Posts how much time is left until the next tweet."
    )
    async def time(self, interaction=Interaction):

        first_tweet_date = datetime.datetime(
            self.first_tweet_date[0],
            self.first_tweet_date[1],
            self.first_tweet_date[2],
            self.first_tweet_date[3],
            self.first_tweet_date[4],
            self.first_tweet_date[5], 
            tzinfo=datetime.timezone.utc)
        todays_date = datetime.datetime.now(datetime.timezone.utc)

        current_offset_from_tweet_time = todays_date - todays_date.replace(hour=2, minute=0, second=0, microsecond=0)
        time_until_next_tweet = datetime.timedelta(days=1) - current_offset_from_tweet_time
        datetime_of_next_tweet = todays_date + time_until_next_tweet
        unix_timestamp = datetime.datetime.timestamp(datetime_of_next_tweet)

        time_since_first_tweet = todays_date - first_tweet_date
        next_tweet_sender = self.pair_names[(time_since_first_tweet.days + 1) % 2]

        await interaction.response.send_message("Next tweet will happen <t:{}:R> and it'll be tweeted by {}.".format(str(unix_timestamp)[:10], next_tweet_sender), ephemeral=self.is_not_in_whitelist(interaction.channel_id))



def setup(bot: commands.Bot):
    bot.add_cog(ARG(bot))
