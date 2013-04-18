#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Enya - a crappy IRC bot that spews NP info
# Copyright (C) 2013 Elizabeth Myers. Licensed under the WTFPL.

from __future__ import print_function, unicode_literals, division

from gevent import socket, monkey, sleep, spawn, joinall
monkey.patch_all()

from irclib.client.client import IRCClient

from collections import namedtuple
from copy import deepcopy

import sys
import traceback

try:
    import config
except ImportError:
    print('Try configuring your bot again! ;)', file=sys.stderr)
    quit()

PY3 = True if sys.version_info[0] == 3 else False

try:
    import urllib.request as urlreq
    from urllib.parse import quote_plus as urlquote
except ImportError:
    import urllib as urlreq
    from urllib import quote_plus as urlquote


import json

try:
    from imp import reload
except ImportError:
    pass


# User configurable parts
APIKEY = config.lastfm_apikey
SECRET = config.lastfm_secret

# TODO: make these not global -.-
user_changed = False

def user_check(irc, line):
    if not line.hostmask:
        return

    nick = line.hostmask.nick
    host = line.hostmask.host

    global config

    if config.auth_type == "admin":
        # XXX ugh, I hate this
        if nick not in config.admin_nicks:
            return

        if host not in config.admin_hosts:
            return
    elif config.auth_type == "account":
        if nick not in irc.users:
            return

        if irc.users[nick].account not in config.admin_accounts:
            return
    else:
        if config.auth_type(irc, line) == None:
            return

    admin = nick

    message = line.params[-1]

    if len(message) <= 1:
        return

    # Check if command
    if message[0] not in ('!', '+', '-'):
        return

    command, sep, message = message[1:].partition(' ')
    command = command.lower()
    message = message.strip()

    if not command:
        return

    if command.startswith('add'):
        add_to_userlist(irc, admin, message)
    elif command.startswith('del'):
        delete_from_userlist(irc, admin, message)
    elif command.startswith('list'):
        userlist = load_users()
        irc.cmdwrite('PRIVMSG', [admin, ' '.join(userlist)])
    elif command.startswith('reload'):
        oldconfig = config
        try:
            reload(config)
        except Exception as e:
            exstr = 'Failed reloading: {}'.format(str(e))
            irc.cmdwrite('PRIVMSG', [admin, exstr])

            # Try to restore old config
            config = oldconfig

def spam_msg(irc, message):
    for ch in irc.channels.values():
        irc.cmdwrite('PRIVMSG', [ch.name, message])

def write_userlist(userlist):
    with open('userlist.txt', 'w') as f:
        f.write('\n'.join(userlist))

def add_to_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if user in userlist:
        irc.cmdwrite('PRIVMSG', [admin, 'Already in there'])
        return
    
    userlist.add(param)
    
    write_userlist(userlist)

    irc.cmdwrite('PRIVMSG', [admin, 'Done!'])
    user_changed = True

def delete_from_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if user not in userlist:
        irc.cmdwrite('PRIVMSG', [admin,  'Not in there.'])
        return
    
    userlist.discard(param)

    write_userlist(userlist)

    irc.cmdwrite('PRIVMSG', [admin, 'Done!'])
    user_changed = True

def load_users():
    temp = set() 
    with open('userlist.txt', 'r') as f:
        temp.update([x.rstrip('\n') for x in f])
    return temp

def dl_json_from(url):
    # Fsck it, we'll do it live, I don't care
    # I know I'll be murdered unpleasantly by a cat, but I like doing things MY WAY, OK - CorgiDude
    try:
        last_sock = urlreq.urlopen(url)
    except Exception as e:
        if str(e) == "HTTP Error 400: Bad Request":
            raise Exception("No user with that name was found")
        else:
            raise
           
    last_json = last_sock.read()
    last_sock.close()
    last_doc = json.loads(last_json)
    return last_doc

def get_np_for(user):
    info = {}
    info['track'] = None
    info['artist'] = None
    info['album'] = None
    
    url = "http://ws.audioscrobbler.com/2.0/?method=user.getRecentTracks&user={user}&limit=1&api_key={key}&format=json".format(user = user, key = APIKEY)
    last_doc = dl_json_from(url)

    if 'recenttracks' not in last_doc:
        return # Nothing to be done.

    if 'track' not in last_doc['recenttracks']:
        return # Nothing to be done

    tracks = last_doc['recenttracks']['track']
    if tracks is None or len(tracks) == 0:
       return None # Punt.  Nothing can be done.

    our_track = None
    for t in tracks:
        if '@attr' in t and 'nowplaying' in t['@attr']:
            our_track = t
            break
 
    if our_track is None: return None

    try:
        info['title'] = our_track['name']
        info['artist'] = our_track['artist']['#text'] # yes, wtf.
        if any(((not x) for x in (info['title'], info['artist']))):
            # Punt.
            return None
    except Exception:
        return None # track name or artist missing, shouldn't scrobble

    try:
        info['album'] = our_track['album']['#text']
        if not info['album']: info['album'] = None
    except Exception:
        info['album'] = None
    
    # makes play count retrieval easier-ish
    try:
        info['mbid'] = our_track['mbid']
        if not info['mbid'] = info['mbid'] = None
    except Exception:
        info['mbid'] = None
    
    return info


def get_counts_for(track, user):
    params = ""
    if track['mbid'] is None:
        params = "artist={artist}&track={track}".format(artist = urlquote(unicode(track['artist']).encode('utf-8', 'replace')),
                                                        track = urlquote(unicode(track['title']).encode('utf-8', 'replace')))
    else:
        params = "mbid={mbid}".format(mbid = track['mbid'])
    url = "http://ws.audioscrobbler.com/2.0/?method=track.getInfo&{params}&username={user}&api_key={key}&format=json".format(user = user, params = params, key = APIKEY)
    last_doc = dl_json_from(url)

    if 'track' not in last_doc:
        return (0, 0, None)

    track = last_doc['track']

    try:
        track_ms = track['duration']
    except Exception:
        track_ms = 0
    
    try:
        play_count = track['userplaycount']
    except Exception:
        play_count = 0
    
    try:
        genre = ', '.join([x['name'] for x in track['toptags']['tag']][:5])
    except Exception:
        genre = None
    
    duration = '{}:{:02d}'.format(*divmod(int(int(track_ms) / 1000), 60))
    return (duration, play_count, genre)

def do_poll(irc):
    global user_changed
    userlist = load_users()
    npcache = {}
    
    for u in userlist:
        npcache[u] = (None,)*6

    while True:
        if user_changed is True:
            userlist = load_users()
            npcache = {}
            
            for u in userlist:
                npcache[u] = (None,)*5
            
            user_changed = False
        
        cache = deepcopy(npcache)
        for k, v in cache.items():
            last = v
            try:
                sleep(1.2)
                track = get_np_for(k)
            except Exception as e:
                if str(e) != "No user with that name was found":
                    raise

                userlist.remove(k)
                del npcache[k]

                print("Error adding user {name}: {exc}".format(name = k, exc = str(e)))
                continue

            if track is None: continue

            artist = track['artist']
            title = track['title']
            album = track['album']
            try:
                duration, count, genre = get_counts_for(track, k)
            except Exception as e:
                duration = count = 0
                genre = None

            np = (artist, title, album, duration, count, genre)
            if last == (None,)*6:
                npcache[k] = np
                continue

            elif last == np:
                continue

            fmt = ("{} is listening to: {} - {} (album: {}) [{}] | "
                   "Playcount: {}x | Genre(s): {}")

            if not PY3:
                fmt = unicode(fmt)

            string = fmt.format(k, *np)
            print(string)

            spam_msg(irc, string)
            npcache[k] = np

def exception_wrapper(irc):
    while True:
        try:
            do_poll(irc)
        except Exception as e:
            spam_msg(irc, "last.fm collector crapped itself. Restarting... some NP's may get lost.")
            print("The reason I crapped all over IRC and it smells real bad is:")
            traceback.print_exc()
            sleep(10)


def run_irc(irc, recurse=0):
    try:
        generator = irc.get_lines()
        for line in generator:
            if line and line.command == 'PRIVMSG':
                user_check(irc, line)
    except Exception as e:
        if not irc.connected:
            print("Disconnected", str(e))
            sleep(5)
        else:
            # Blargh
            print("Probable non-fatal exception received:")
            traceback.print_exc()
            if recurse >= 10:
                print("Recursion depth exceeded for errors")
                irc.close()
                raise
            recurse += 1
            run_irc(irc, recurse)

irc = IRCClient(nick=config.nick, user=config.user, host=config.server,
                port=config.port, realname=config.realname,
                channels=config.channels)
irc.connect()

g1 = spawn(run_irc, irc)
g2 = spawn(exception_wrapper, irc=irc)

joinall((g1, g2))

