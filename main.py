#!/usr/bin/env python3
# Enya - a crappy IRC bot that spews NP info
# Copyright (C) 2013 Elizabeth Myers. Licensed under the WTFPL.

from gevent import socket, monkey, sleep, spawn, joinall
monkey.patch_all()

from collections import namedtuple
from copy import deepcopy
from settings import server,port,nick,user,realname,channels
import urllib.request as urlreq
from urllib.parse import quote_plus as urlquote
import xml.dom.minidom as minidom

# User configurable parts
USERNAME = "therealelizacat"
PASSWORD = "499c2d7ae9b60028c286c6b20f8f3d81" # pylast.md5() - hint.
APIKEY = "bf68f12315aea1b0b08b782cd5f59ad9"
SECRET = "22fea42e3a87dd0d4a0b44cd5bf156b5"

admin_nicks = ['Elizacat',]
admin_hosts = ['always.lowing.the.bar',]
# None below here

# TODO: make these not global -.-
user_changed = False

def maybe_add_to_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if param in userlist:
        irc.send(self.parsed_line(None, "PRIVMSG", [admin, 'Already in there.']))
        return
    
    userlist.append(param)
    
    with open('userlist.txt', 'w') as f:
        for l in userlist:
            f.write('\n'.join(userlist))

    irc.send(self.parsed_line(None, "PRIVMSG", [admin, 'Done!']))
    user_changed = True

def maybe_del_from_userlist(irc, admin, user):
    global user_changed
    userlist = load_users()
    if param not in userlist:
        self.send(self.parsed_line(None, "PRIVMSG", [admin,  'Not in there.']))
        return
    
    userlist.remove(param)
    
    with open('userlist.txt', 'w') as f:
        for l in userlist:
            f.write('\n'.join(userlist))
    
    irc.send(self.parsed_line(None, "PRIVMSG", [admin, 'Done!']))
    user_changed = True

class IRC:
    # TODO - WOAH FIX THIS PIECE OF SHIT
    def __init__(self, nick, user, server, port, realname, channels):
        self.nick = nick
        self.user = user
        self.server = server
        self.port = port
        self.realname = realname
        self.channels = channels

        # Commands
        self.commands = dict()
        self.commands['NOTICE'] = self.do_notice
        self.commands['PRIVMSG'] = self.do_privmsg
        self.commands['PING'] = self.do_ping
        self.commands['001'] = self.do_welcome

        self.serv_reg = False

        self.parsed_line = namedtuple("ParsedLine", ["hostmask", "command", "params"])

    def parse(self, line):
        line = line.rstrip('\r\n')
        line, sep, lparam = line.partition(' :')

        line = line.split()
        if lparam is not None:
            line.append(lparam)

        if line[0][0] == ':':
            hostmask = line[0][1:]
            command = line[1]
            if len(line) > 2:
                params = line[2:]
            else:
                params = []
        else:
            hostmask = None
            command = line[0]
            if len(line) > 1:
                params = line[1:]
            else:
                params = []

        return self.parsed_line(hostmask, command, params)

    def connect(self):
        self.sock = socket.socket()
        self.sock.connect((self.server, self.port))

    def send(self, line):
        out = []
        if line.hostmask:
            out.append(':' + line.hostmask)

        out.append(line.command)

        if line.params != []:
            if line.params[-1].find(' ') != -1:
                if len(line.params) > 1:
                    out.extend(line.params[:-1])
                out.append(':' + line.params[-1])
            else:
                out.extend(line.params)

        s = ' '.join(out)
        print(">", s)
        s += '\r\n'
        self.sock.send(s.encode('UTF-8'))

    def do_notice(self, line):
        if not self.serv_reg:
            self.send(self.parsed_line(None, 'USER', [self.user, '*', '*', self.realname]))
            self.send(self.parsed_line(None, 'NICK', [self.nick]))

            self.serv_reg = True

    def do_privmsg(self, line):
        # FIXME shitty.
        if line.hostmask is not None:
            x, sep, y = line.hostmask.partition('@')
            if sep is None or y is None: return

            if y not in admin_hosts: return
            x, sep, y = x.partition('!')
            if True not in [x.startswith(nick) for nick in admin_nicks]: return # XXX this is disgusting

            msg = line.params[-1]
            cmd, sep, param = msg.partition(' ')
            cmd = cmd.lower()

            if not cmd:
                print("Empty message ", msg)
                return

            if cmd[0] != '!':
                return
            else:
                cmd = cmd[1:]

            if cmd == 'add':
                maybe_add_to_userlist(self, x, param)

            elif cmd == 'del':
                maybe_delete_from_userlist(self, x, param)

            elif cmd == 'list':
                self.send(self.parsed_line(None, "PRIVMSG", [x, ' '.join(load_users())]))

    def do_ping(self, line):
        self.send(self.parsed_line(None, "PONG", line.params))

    def do_welcome(self, line):
        self.send(self.parsed_line(None, "JOIN", [','.join(self.channels)]))

    def spam_msg(self, message):
        for channel in self.channels:
            self.send(self.parsed_line(None, "PRIVMSG", [channel, message]))

    def dispatch(self):
        buf = []
        while True:
            self.sock.send(b'\r\n')
            s = self.sock.recv(4096)
            buf.append(s.decode('UTF-8'))

            f = ''.join(buf)
            f = f.split('\r\n')
            if f[-1] != '':
                buf = [f[-1]]
            else:
                buf = []

            del f[-1]

            for x in f:
                print("<",x)
                p = self.parse(x)
                if p.command in self.commands:
                    self.commands[p.command](p)

def load_users():
    temp = []
    with open('userlist.txt', 'r') as f:
        temp = [x.rstrip('\n') for x in f]
    return temp

def dl_xml_from(url):
    # Fsck it, we'll do it live, I don't care
    # I know I'll be murdered unpleasantly by a cat, but I like doing things MY WAY, OK
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
    if tracks is None:
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
    print(url)
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
            irc.spam_msg(string)
            npcache[k] = np

def exception_wrapper(irc):
    while True:
        try:
            do_poll(irc)
        except Exception as e:
            irc.spam_msg("last.fm collector crapped itself. Restarting... some NP's may get lost.")
            print("The reason I crapped all over IRC and it smells real bad is: ({extype}) {exc}".format(extype = type(e), exc = e))
            sleep(10)

f = IRC(nick, user, server, port, realname, channels)
f.connect()
g1 = spawn(f.dispatch)

g2 = spawn(exception_wrapper, irc=f)

joinall((g1, g2))

