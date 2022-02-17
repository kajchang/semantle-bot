import discord
from dotenv import load_dotenv
import aiohttp
import dbm
import json
import numpy as np

from datetime import datetime
import os

load_dotenv()

client = discord.Client()

CHANNEL_NAME = 'semantle'

db = dbm.open('semantle.db', 'c')

HEADER = '**Semantle {}**'

def format_guess(guess):
  return '{} - {} ({})'.format(guess[0] + 1, guess[1], str(round(guess[2], 2)))

def generate_message_content(date, guesses):
  guesses_by_score = sorted(guesses[:-1], key=lambda x: x[2])
  content = HEADER.format(date)
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
    current_utc_date = datetime.utcnow().strftime("%m/%d/%Y")
    if semantle_date is None or semantle_date != current_utc_date:
      db['semantle_date'] = current_utc_date
      semantle_date = current_utc_date

      async with aiohttp.ClientSession() as session:
        async with session.get('https://semantle.novalis.org/model2/tail/tail') as response:
          data = await response.json()
          db['semantle_most_vec'] = json.dumps(data['vec'])
        async with session.get('https://semantle.novalis.org/similarity/tail') as response:
          data = await response.json()
          db['semantle_most_similarity'] = json.dumps(data)
    
    async with aiohttp.ClientSession() as session:
      async with session.get('https://semantle.novalis.org/model2/tail/{}'.format(message.content)) as response:
        if response.headers['Content-Type'] == 'application/json':
          data = await response.json()
          semantle_data = json.loads(db.get('semantle_most_vec'))
          word = message.content
          score = np.dot(data['vec'], semantle_data) / (np.linalg.norm(data['vec']) * np.linalg.norm(semantle_data))

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
      await message.channel.send('{} got the word: {}'.format(message.author.mention, word))

    result_message = None
    for message_to_check in await output_channel.history(limit=100).flatten():
      if message_to_check.content.startswith(HEADER.format(semantle_date)):
        result_message = message_to_check
        break

    if result_message is None:
      await output_channel.send(generate_message_content(semantle_date, guesses))
    else:
      await result_message.edit(content=generate_message_content(semantle_date, guesses))

    await message.delete()

client.run(os.getenv('TOKEN'))
