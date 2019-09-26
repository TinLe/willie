# coding=utf-8
"""
tell.py - Sopel Tell and Ask Module
Copyright 2008, Sean B. Palmer, inamidst.com
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import unicode_literals, absolute_import, print_function, division

import io
import os
import time
import threading
from collections import defaultdict

from sopel.module import commands, nickname_commands, rule, priority, example
from sopel.tools import Identifier
from sopel.tools.time import get_timezone, format_time


MAXIMUM = 4


def load_reminders(filename):
    """Load tell/ask reminders from a ``filename``.

    :param str filename: path to the tell/ask reminders file
    :return: a dict with the tell/asl reminders
    :rtype: dict
    """
    result = defaultdict(list)
    with io.open(filename, 'r', encoding='utf-8') as fd:
        for line in fd:
            line = line.strip()
            if line:
                try:
                    tellee, teller, verb, timenow, msg = line.split('\t', 4)
                except ValueError:
                    continue  # TODO: Add warning log about malformed reminder
                result[tellee].append((teller, verb, timenow, msg))

    return result


def dump_reminders(filename, data):
    """Dump tell/ask reminders (``data``) into a ``filename``.

    :param str filename: path to the tell/ask reminders file
    :param dict data: tell/ask reminders ``dict``
    """
    with io.open(filename, 'w', encoding='utf-8') as fd:
        for tellee, reminders in data.items():
            for reminder in reminders:
                line = '\t'.join((tellee,) + tuple(reminder))
                fd.write(line + '\n')
    return True


def setup(bot):
    fn = bot.nick + '-' + bot.config.core.host + '.tell.db'
    bot.tell_filename = os.path.join(bot.config.core.homedir, fn)

    if not os.path.exists(bot.tell_filename):
        with io.open(bot.tell_filename, 'w', encoding='utf-8') as fd:
            # if we can't open/write into the file, the tell plugin can't work
            fd.write('')

    if 'tell_lock' not in bot.memory:
        bot.memory['tell_lock'] = threading.Lock()

    if 'reminders' not in bot.memory:
        with bot.memory['tell_lock']:
            bot.memory['reminders'] = load_reminders(bot.tell_filename)


def shutdown(bot):
    for key in ['tell_lock', 'reminders']:
        try:
            del bot.memory[key]
        except KeyError:
            pass


@commands('tell', 'ask')
@nickname_commands('tell', 'ask')
@example('$nickname, tell dgw he broke something again.')
def f_remind(bot, trigger):
    """Give someone a message the next time they're seen"""
    teller = trigger.nick
    verb = trigger.group(1)

    if not trigger.group(3):
        bot.reply("%s whom?" % verb)
        return

    tellee = trigger.group(3).rstrip('.,:;')
    msg = trigger.group(2).lstrip(tellee).lstrip()

    if not msg:
        bot.reply("%s %s what?" % (verb, tellee))
        return

    tellee = Identifier(tellee)

    if not os.path.exists(bot.tell_filename):
        return

    if len(tellee) > 30:  # TODO: use server NICKLEN here when available
        return bot.reply('That nickname is too long.')
    if tellee == bot.nick:
        return bot.reply("I'm here now; you can tell me whatever you want!")

    if tellee not in (Identifier(teller), bot.nick, 'me'):
        tz = get_timezone(bot.db, bot.config, None, tellee)
        timenow = format_time(bot.db, bot.config, tz, tellee)
        with bot.memory['tell_lock']:
            if tellee not in bot.memory['reminders']:
                bot.memory['reminders'][tellee] = [(teller, verb, timenow, msg)]
            else:
                bot.memory['reminders'][tellee].append((teller, verb, timenow, msg))
            # save the reminders
            dump_reminders(bot.tell_filename, bot.memory['reminders'])

        response = "I'll pass that on when %s is around." % tellee
        bot.reply(response)
    elif Identifier(teller) == tellee:
        bot.say('You can %s yourself that.' % verb)
    else:
        bot.say("Hey, I'm not as stupid as Monty you know!")


def getReminders(bot, channel, key, tellee):
    lines = []
    template = "%s: %s <%s> %s %s %s"
    today = time.strftime('%d %b', time.gmtime())

    bot.memory['tell_lock'].acquire()
    try:
        for (teller, verb, datetime, msg) in bot.memory['reminders'][key]:
            if datetime.startswith(today):
                datetime = datetime[len(today) + 1:]
            lines.append(template % (tellee, datetime, teller, verb, tellee, msg))

        try:
            del bot.memory['reminders'][key]
        except KeyError:
            bot.say('Er…', channel)
    finally:
        bot.memory['tell_lock'].release()
    return lines


@rule('(.*)')
@priority('low')
def message(bot, trigger):

    tellee = trigger.nick
    channel = trigger.sender

    if not os.path.exists(bot.tell_filename):
        return

    reminders = []
    remkeys = list(reversed(sorted(bot.memory['reminders'].keys())))

    for remkey in remkeys:
        if not remkey.endswith('*') or remkey.endswith(':'):
            if tellee.lower() == remkey.lower():
                reminders.extend(getReminders(bot, channel, remkey, tellee))
        elif tellee.lower().startswith(remkey.lower().rstrip('*:')):
            reminders.extend(getReminders(bot, channel, remkey, tellee))

    for line in reminders[:MAXIMUM]:
        bot.say(line)

    if reminders[MAXIMUM:]:
        bot.say('Further messages sent privately')
        for line in reminders[MAXIMUM:]:
            bot.say(line, tellee)

    if len(bot.memory['reminders'].keys()) != remkeys:
        with bot.memory['tell_lock']:
            dump_reminders(bot.tell_filename, bot.memory['reminders'])  # @@ tell
