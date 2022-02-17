import discord
from dotenv import load_dotenv
import aiohttp
import dbm
import json
import math
import numpy as np

from datetime import datetime
import os

from secret_words import secret_words

load_dotenv()

client = discord.Client()

CHANNEL_NAME = 'semantle'

db = dbm.open('semantle.db', 'c')

HEADER = '**Semantle #{}**'

def format_guess(guess):
  return '#{} - **{}** ({})'.format(guess[0] + 1, guess[1], round(guess[2], 2))

def generate_message_content(puzzle_number, guesses):
  guesses_by_score = sorted(guesses[:-1], key=lambda x: x[2])
  content = HEADER.format(puzzle_number)
  content += '\n'
  content += '**Latest Guess:**\n'
  content += format_guess(guesses[-1])
  content += '\n'
  content += '**------------**\n'
  
  while True:
    if len(guesses_by_score) == 0:
      break
    guess_content = format_guess(guesses_by_score.pop())
    if len(guess_content) + len(content) > 2000:
      break
    content += guess_content
    content += '\n'

  return content

@client.event
async def on_ready():
  print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
  if message.author == client.user:
    return

  if message.channel.name == CHANNEL_NAME:
    output_channel = message.channel

    semantle_date = db.get('semantle_date')
    if semantle_date is not None:
      semantle_date = int(semantle_date)

    now = datetime.utcnow().timestamp()
    today = math.floor(now / 86400) - 1
    initial_day = 19021
    puzzle_number = (today - initial_day) % len(secret_words)

    secret_word = secret_words[puzzle_number]
    db['semantle_secret_word'] = secret_word

    if semantle_date is None or semantle_date != today:
      db['semantle_date'] = str(today)
      semantle_date = today

      async with aiohttp.ClientSession() as session:
        async with session.get('https://semantle.novalis.org/model2/{0}/{0}'.format(secret_word)) as response:
          data = await response.json()
          db['semantle_most_vec'] = json.dumps(data['vec'])
        async with session.get('https://semantle.novalis.org/similarity/tail') as response:
          data = await response.json()
          db['semantle_most_similarity'] = json.dumps(data)

    async with aiohttp.ClientSession() as session:
      async with session.get('https://semantle.novalis.org/model2/{}/{}'.format(secret_word, message.content.strip())) as response:
        if response.headers['Content-Type'] == 'application/json':
          data = await response.json()
          semantle_data = json.loads(db.get('semantle_most_vec'))
          word = message.content
          score = np.dot(data['vec'], semantle_data) / (np.linalg.norm(data['vec']) * np.linalg.norm(semantle_data))
        else:
          await message.delete()

    guesses_cache_key = '{}.{}.guesses'.format(message.guild.id, semantle_date)
    guesses = db.get(guesses_cache_key)

    if guesses is None:
      guesses = []
    else:
      guesses = json.loads(guesses)
    if len(list(filter(lambda x: x[1] == word, guesses))) == 0:
      guesses.append([len(guesses), word, score * 100])
    db[guesses_cache_key] = json.dumps(guesses)

    if score * 100 == 100:
      await message.channel.send('{} got the word: **{}**'.format(message.author.mention, word))

    result_message = None
    for message_to_check in await output_channel.history(limit=100).flatten():
      if message_to_check.content.startswith(HEADER.format(puzzle_number)):
        result_message = message_to_check
        break

    if result_message is None:
      await output_channel.send(generate_message_content(puzzle_number, guesses))
    else:
      await result_message.edit(content=generate_message_content(puzzle_number, guesses))

    await message.delete()

client.run(os.getenv('TOKEN'))
