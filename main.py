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

from settings import *

try:
    import urllib.request as urlreq
    from urllib.parse import quote_plus as urlquote
except ImportError:
    import urllib as urlreq
    from urllib import quote_plus as urlquote

import xml.dom.minidom as minidom


# User configurable parts
APIKEY = lastfm_apikey
SECRET = lastfm_secret

# TODO: make these not global -.-
user_changed = False

def user_check(irc, line):
    if not line.hostmask:
        return

    # XXX ugh, I hate this
    if line.hostmask.nick not in admin_nicks:
        return

    if line.hostmask.host not in admin_hosts:
        return

    admin = line.hostmask.nick

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

def spam_msg(irc, message):
    for ch in irc.channels.values():
        irc.cmdwrite('PRIVMSG', [ch.name, message])

def write_userlist(userlist):
    with open('userlist.txt', 'w') as f:
        f.write('\n'.join(userlist))

def add_to_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if param in userlist:
        irc.cmdwrite('PRIVMSG', [admin, 'Already in there'])
        return
    
    userlist.append(param)
    
    write_userlist(userlist)

    irc.cmdwrite('PRIVMSG', [admin, 'Done!'])
    user_changed = True

def delete_from_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if param not in userlist:
        irc.cmdwrite('PRIVMSG', [admin,  'Not in there.'])
        return
    
    userlist.remove(param)

    write_userlist(userlist)

    irc.cmdwrite('PRIVMSG', [admin, 'Done!'])
    user_changed = True

def load_users():
    temp = []
    with open('userlist.txt', 'r') as f:
        temp = [x.rstrip('\n') for x in f]
    return temp

def dl_xml_from(url):
    # Fsck it, we'll do it live, I don't care
    # I know I'll be murdered unpleasantly by a cat, but I like doing things MY WAY, OK - CorgiDude
    try:
        last_sock = urlreq.urlopen(url)
    except Exception as e:
        if str(e) == "HTTP Error 400: Bad Request":
            raise Exception("No user with that name was found")
        else:
            raise e
           
    last_xml = last_sock.read()
    last_sock.close()
    last_doc = minidom.parseString(last_xml)
    return last_doc

def get_np_for(user):
    info = {}
    info['track'] = None
    info['artist'] = None
    info['album'] = None
    
    url = "http://ws.audioscrobbler.com/2.0/?method=user.getRecentTracks&user={user}&limit=1&api_key={key}".format(user = user, key = APIKEY)
    last_doc = dl_xml_from(url)
    tracks = last_doc.getElementsByTagName("track")
    if tracks is None or len(tracks) == 0:
       return None # Punt.  Nothing can be done.

    our_track = tracks[0]
    try:
        info['title'] = our_track.getElementsByTagName("name")[0].childNodes[0].data
        info['artist'] = our_track.getElementsByTagName("artist")[0].childNodes[0].data
    except:
        return None  # track name or artist missing, shouldn't scrobble
    
    try:
        info['album'] = our_track.getElementsByTagName("album")[0].childNodes[0].data
    except:
        info['album'] = None
    
    # makes play count retrieval easier-ish
    try:
        info['mbid'] = our_track.getElementsByTagName("mbid")[0].childNodes[0].data
    except:
        info['mbid'] = None
    
    return info


def get_counts_for(track, user):
    params = ""
    if track['mbid'] is None:
        params = "artist={artist}&track={track}".format(artist = urlquote(track['artist']), track = urlquote(track['title']))
    else:
        params = "mbid={mbid}".format(mbid = track['mbid'])
    url = "http://ws.audioscrobbler.com/2.0/?method=track.getInfo&{params}&username={user}&api_key={key}".format(user = user, params = params, key = APIKEY)
    last_doc = dl_xml_from(url)

    try:
        track_ms = last_doc.getElementsByTagName("duration")[0].childNodes[0].data
    except:
        track_ms = 0
    
    try:
        play_count = last_doc.getElementsByTagName("userplaycount")[0].childNodes[0].data
    except:
        play_count = 0
    
    duration = '{}:{:02d}'.format(*divmod(int(int(track_ms) / 1000), 60))
    return (duration, play_count)

def do_poll(irc):
    global user_changed
    userlist = load_users()
    npcache = {}
    
    for u in userlist:
        npcache[u] = (None,)*5

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
                    raise e
                
                userlist.remove(k)
                del npcache[k]

                print("Error adding user {name}: {exc}".format(name = k, exc = str(e)))
                continue

            if track is None: continue

            artist = track['artist']
            title = track['title']
            album = track['album']
            try:
                duration, count = get_counts_for(track, k)
            except:
                duration = count = 0

            np = (artist, title, album, duration, count)
            if last == (None,)*5:
                npcache[k] = np
                continue

            elif last == np:
                continue

            string = "{} is listening to: {} - {} (album: {}) [{}] | Playcount: {}x".format(k, *np)
            print(string)
    
            spam_msg(irc, string)
            npcache[k] = np

def exception_wrapper(irc):
    while True:
        try:
            do_poll(irc)
        except Exception as e:
            spam_msg(irc, "last.fm collector crapped itself. Restarting... some NP's may get lost.")
            print("The reason I crapped all over IRC and it smells real bad is: ({extype}) {exc}".format(extype = type(e), exc = e))
            sleep(10)


def run_irc(irc):
    try:
        generator = irc.get_lines()
        for line in generator:
            if line and line.command == 'PRIVMSG':
                user_check(irc, line)
    except IOError as e:
        print("Disconnected", str(e))
        sleep(5) 

irc = IRCClient(nick=nick, user=user, host=server, port=port,
                realname=realname, channels=channels)
irc.connect()

g1 = spawn(run_irc, irc)
g2 = spawn(exception_wrapper, irc=irc)

joinall((g1, g2))

