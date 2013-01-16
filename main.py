#!/usr/bin/env python
# Enya - a crappy IRC bot that spews NP info
# Copyright (C) 2013 Elizabeth Myers. Licensed under the WTFPL.

from gevent import socket, monkey, sleep, spawn, joinall
monkey.patch_all()

import pylast
from collections import namedtuple
from copy import deepcopy

# User configurable parts
USERNAME = "changeme"
PASSWORD = "changeme" # pylast.md5(string)
APIKEY = "get from http://last.fm/api"
SECRET = "get from http://last.fm/api"

server = "irc.interlinked.me"
port = 6667
nick = user = "Enya"
realname = "Your worst nightmare."
channels = ["#enya"]

# None below here

# TODO: make these not global -.-
with open('userlist.txt', 'r') as f:
    userlist = [x.rstrip('\n') for x in f]
npcache = {}

class IRC:
    # TODO - WOAH FIX THIS PIECE OF SHIT
    def __init__(self, nick, user, server, port, realname, channels):
        self.nick = nick
        sAelf.user = user
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

            # FIXME - configurable auth...
            # Change 'this to your host
            if y != 'always.lowering.the.bar': return

            x, sep, y = x.partition('!')
            if not x.startswith('Elizacat'): return # Change to your nick

            msg = line.params[-1]
            cmd, sep, param = msg.partition(' ')
            cmd = cmd.lower()

            if cmd[0] != '!':
                return
            else:
                cmd = cmd[1:]

            # Change these nicks below too etc.
            if cmd == 'add':
                if param in userlist:
                    self.send(self.parsed_line(None, "PRIVMSG", ['Elizacat', 'Already in there.']))
                    return

                userlist.append(param)
                npcache[param] = ((None,)*5, None)

                with open('userlist.txt', 'w') as f:
                    for l in userlist:
                        f.write('\n'.join(userlist))

                self.send(self.parsed_line(None, "PRIVMSG", ['Elizacat', 'Done!']))

            elif cmd == 'del':
                if param not in userlist:
                    self.send(self.parsed_line(None, "PRIVMSG", ['Elizacat',  'Not in there.']))
                    return

                userlist.remove(param)

                if param in npcache:
                    del npcache[param]

                with open('userlist.txt', 'w') as f:
                    for l in userlist:
                        f.write('\n'.join(userlist))

                self.send(self.parsed_line(None, "PRIVMSG", ['Elizacat', 'Done!']))

            elif cmd == 'list':
                self.send(self.parsed_line(None, "PRIVMSG", ['Elizacat', ' '.join(userlist)]))

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

def do_poll(lastfm, irc):
    # FIXME encapsulate
    for u in userlist:
        npcache[u] = ((None,)*5, None)

    while True:
        cache = deepcopy(npcache)
        for k, v in cache.items():
            last, uinstance = v
            if uinstance is None:
                uinstance = pylast.User(k, lastfm)

            try:
                track = uinstance.get_now_playing()
            except pylast.WSError as e:
                if str(e) != "No user with that name was found":
                    raise e
                
                userlist.remove(k)
                del npcache[k]

                print("Error adding user k: {}".format(str(e)))
                continue

            if track is None: continue

            artist = track.get_artist()
            if artist:
                artist = artist.get_name()
            else:
                artist = "[No artist]"

            title = track.get_title()

            album = track.get_album()
            if album:
                album = album.get_name()
            else:
                album = "None"

            duration = '{}:{:02d}'.format(*divmod(int(track.get_duration() / 1000), 60))
            try:
                count = track.get_userplaycount() # NOTE - requires https://github.com/Elizacat/pylast 
            except:
                count = 0

            np = (artist, title, album, duration, count)
            if last == (None,)*5:
                npcache[k] = (np, uinstance)
                continue

            elif last == np:
                continue

            string = "{} is listening to: {} - {} (album: {}) [{}] | Playcount: {}x".format(k, *np)
            print(string)
            irc.spam_msg(string)
            npcache[k] = (np, uinstance)

        sleep(10)


f = IRC(nick, user, server, port, realname, channels)
f.connect()
g1 = spawn(f.dispatch)

network = pylast.LastFMNetwork(api_key = APIKEY, api_secret = SECRET, username = USERNAME, password_hash = PASSWORD)
g2 = spawn(do_poll, *(network, f))

joinall((g1, g2))

