from collections import namedtuple
import uuid
import os
import datetime
import json
import re

from flask import Flask  
from flask import render_template  
from flask import request
from flask import abort
from flask import redirect
from flask import url_for
from flask import session
from flask import g
from flask_socketio import SocketIO
from flask_socketio import join_room, leave_room, rooms
from flask_socketio import emit
from flask.ext.openid import OpenID
from bidict import bidict

from brawlbracket import brawlapi
from brawlbracket import usermanager as um
from brawlbracket import tournamentmanager as tm
from brawlbracket import chatmanager as cm
from brawlbracket import util

__version__ = '0.1.0'

app = Flask(__name__, static_folder='dist/static', template_folder='dist/templates')
app.secret_key = os.environ.get('BB_SECRET_KEY')
socketio = SocketIO(app)
oid = OpenID(app)

_steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')

# Start temp tournament generation
steamIds = [76561198045082103, 76561198065399638, 76561198072175457,
            76561198069178478, 76561198078549692, 76561197995127703,
            76561198068388037, 76561198042414835, 76561197993702532,
            76561198063265824, 76561198042403860, 76561198050490587]
#steamIds = [76561197993702532, 76561197995127703, 76561198045082103,
#            76561198042414835]
tempUsers = []
for id in steamIds:
    user = um.getUserBySteamId(id)
    if user is None:
        user = um.createUser(id)
    tempUsers.append(user)
tempTourney = tm.getTournamentByName('test')
if tempTourney is None:
    tempTourney = tm.createTournament(
                    'test',
                    name='BrawlBracket Test Tourney'
                    )
    tempTourney.addAdmins(um.getUserBySteamId(76561198042414835),
                          um.getUserBySteamId(76561197993702532))
#                          um.getUserBySteamId(76561197995127703))

if False:
    for i, user in enumerate(tempUsers):
        team = tempTourney.createTeam(i + 1) # i = seed, 1-indexed
        team.name = user.username
        player = tempTourney.createPlayer(user)
        team.players.append(player)
        print(team)
    print('Temp tournament has {} users!'.format(len(tempTourney.teams)))
    tempTourney.generateMatches()
    
    
    print('Admins: ', [a.username for a in tempTourney.admins])
# End temp tournament generation
    
@app.context_processor
def default_template_data():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    
    return dict(versionNumber = __version__,
                user = user)
                
@app.template_filter('datetime')
def filter_datetime(date):
    """
    Filter to format a Python datetime.
    """
    return date.strftime('%B %d, %Y @ %I:%M %p %Z')
    
@app.template_filter('timedelta')
def filter_timedelta(time):
    """
    Filter to format a Python timedelta.
    """
    hours, remainder = divmod(time.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    tokens = []
    if hours > 0:
        tokens.append('{} hour'.format(hours) + ('s' if hours > 1 else ''))
        
    if minutes > 0:
        tokens.append('{} minute'.format(minutes) + ('s' if minutes > 1 else ''))
    
    return ', '.join(tokens)
    
#----- Flask routing -----#
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/login/')
@oid.loginhandler
def login():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    
    if user is None:
        if userId is not None:
            session.pop('userId')
        
        return oid.try_login('http://steamcommunity.com/openid')
    else:
        return redirect(oid.get_next_url())

@app.route('/logout/')
def logout():
    session.pop('userId')
    return redirect(oid.get_next_url())

@oid.after_login
def createOrLogin(resp):
    match = _steam_id_re.search(resp.identity_url)
    match = int(match.group(1))
    
    user = um.getUserBySteamId(match)
    if user is None:
        user = um.createUser(match)
        
        if user is None:
            print('Couldn\'t make user!')
            return
    
    print(user) # DEBUG
    session['userId'] = user.id
    return redirect(oid.get_next_url())
    
@app.route('/')
@app.route('/index/')
def index():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    if user is not None:
        return render_template('user-tournaments.html')
        
    else:
        return render_template('index.html')
        brawlapi.init_example_db()
    
# Settings page
@app.route('/settings/', methods=['GET', 'PUT'])
def user_settings():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    
    if user is None:
        print('User doesn\'t exist; returned to index.')
        return redirect(url_for('index'))
    
    if request.method == 'GET':
        return render_template('settings.html',
                               legendData=util.orderedLegends,
                               serverRegions=util.orderedRegions)
                               
    elif request.method == 'PUT':
        if user.setSettings(request.json):
            return json.dumps({'success': True}), 200
            
        else:
            return json.dumps({'success': False}), 500

# Tournament index page
@app.route('/t/<tourneyName>/', methods=['GET', 'POST'])
def tournament_index(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    
    if tournament is None:
        abort(404)
        
    if request.method == 'POST':
        userId = session.get('userId')
        user = um.getUserById(userId)
        
        # Not logged in and trying to register
        if user is None:
            return
        
        existing = False
        for player in tournament.players:
            if player.user.id == user.id:
                existing = True
                break
        
        if not existing:
            team = tournament.createTeam(
                len(tournament.teams) + 1,
                name = user.username)
            
            player = tournament.createPlayer(user)
            
            team.addPlayer(player)
            
            print('ADDED TEAM: {}, PLAYERS: {}'.format(team, team.players))
            print('TOURNAMENT NOW HAS {} TEAMS'.format(len(tournament.teams)))
        else:
            print('ADD TEAM FAILED, ALREADY JOINED! {}'.format(user.username))
        
    
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('tournament.html',
                           tourneyName=tourneyName,
                           tournament=tournament)

@app.route('/t/<tourneyName>/finalize')
def finalize(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    
    if tournament is None:
        abort(404)
    
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    if user is None:
        print('User doesn\'t exist; returned to index.')
        return redirect(url_for('tournament_index', tourneyName=tourneyName))
    
    if tournament.isAdmin(user):
        print('FINALIZING TOURNAMENT')
        print('Tournament has {} users!'.format(len(tournament.teams)))
        tournament.generateMatches()
        print(tournament)
        print('Tournament has {} matches!'.format(len(tournament.matches)))
    
    return redirect(url_for('tournament_index', tourneyName=tourneyName))

#----- User pages -----#

# User app page
@app.route('/t/<tourneyName>/app/', defaults={'startPage': None})
@app.route('/t/<tourneyName>/app/<startPage>/')
def user_app(tourneyName, startPage):
    if not tm.tournamentNameExists(tourneyName):
        abort(404)
    
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    if user is None:
        print('User doesn\'t exist; returned to index.')
        return redirect(url_for('tournament_index', tourneyName=tourneyName))

    tournament = tm.getTournamentByName(tourneyName)
    session['tourneyId'] = tournament.id
    
    
    return render_template('app/user-app.html',
                           startPage=startPage,
                           tourneyName=tourneyName,
                           tournament=tournament,
                           basePath='/t/{}/app/'.format(tourneyName))

# Contact admin page
@app.route('/app-pages/contact-admin/<tourneyName>')
def contact_admin(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('app/pages/contact-admin.html',
                           tournament=tournament,
                           tourneyName=tourneyName)
    
# App version of tournament index
@app.route('/app-pages/index/<tourneyName>')
def app_tournament_index(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)

    return render_template('app/pages/tournament-index.html',
                           tourneyName=tourneyName,
                           tournament=tournament)
    
# Lobby content
@app.route('/app-pages/lobby/<tourneyName>')
def lobby(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('app/pages/lobby.html',
                           tournament=tournament,
                           tourneyName=tourneyName,
                           legendData=util.orderedLegends,
                           realmData=[(id, util.realmData[id]) for id in util.eslRealms])

#----- Admin pages -----#
                           
# Admin app page
@app.route('/t/<tourneyName>/admin/', defaults={'startPage': None})
@app.route('/t/<tourneyName>/admin/<startPage>/')
def admin_app(tourneyName, startPage):
    tournament = tm.getTournamentByName(tourneyName)
    userId = session.get('userId')
    user = um.getUserById(userId)
    
    if tournament is None:
        abort(404)
    
    if user is None:
        return redirect(url_for('tournament_index', tourneyName = tourneyName))
    
    if not tournament.isAdmin(user):
        abort(403)

    return render_template('app/admin-app.html',
                           startPage=startPage,
                           tourneyName=tourneyName,
                           tournament=tournament,
                           basePath='/t/{}/admin/'.format(tourneyName))
                           
# Admin dashboard
@app.route('/app-pages/admin-dashboard/<tourneyName>')
def admin_dashboard(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    userId = session.get('userId')
    user = um.getUserById(userId)
    
    if tournament is None:
        abort(404)
    
    if user is None:
        return redirect(url_for('tournament_index', tourneyName = tourneyName))
    
    if not tournament.isAdmin(user):
        abort(403)

    return render_template('app/pages/admin-dashboard.html',
                           tournament=tournament,
                           tourneyName=tourneyName)
    
#----- Page elements -----#
    
# Connect error
@app.route('/app-elements/lobby-error/<tourneyName>')
def lobby_error(tourneyName):
    return render_template('app/elements/lobby-error.html')
    
# Legend roster
@app.route('/app-elements/roster')
def roster():
    return render_template('app/elements/lobby-roster.html',
    legendData=util.orderedLegends)
    
# Map picker
@app.route('/app-elements/realms')
def realms():
    return render_template('app/elements/lobby-realms.html',
                           realmData=util.orderedRealms)

#----- Raw data -----#

# Lobby data
@app.route('/app-data/lobbies/<tourneyName>')
def data_lobbies(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    
    if tournament is None:
        abort(404)

    # Get a condensed list of lobby data for display to the admin
    condensedData = []

    for match in tournament.matches:
        # Assemble score string 
        scoreString = '-'.join([str(s) for s in match.score])
            
        # Add on bestOf value (e.g. best of 3)
        scoreString += ' (Bo{})'.format(match.bestOf)
        
        status, prettyStatus, statusOrder = match.lobbyStatus
        
        condensed = {
            'id': match.number,
            't1Name': match.teams[0].name if match.teams[0] is not None else '',
            't2Name': match.teams[1].name if match.teams[1] is not None else '',
            'score': scoreString,
            'room': match.roomNumber if match.roomNumber is not None else '',
            'startTime': match.startTime.isoformat()\
                if match.startTime is not None else '',
            'status': {
                'state': status,
                'display': prettyStatus,
                'sort': statusOrder
            }
        }
        
        condensedData.append(condensed)
        
    ajaxData = {
        'data': condensedData
    }
    
    return json.dumps(ajaxData)
    
# User data
@app.route('/app-data/teams/<tourneyName>')
def data_teams(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    
    if tournament is None:
        abort(404)
    
    # Get a condensed list of user data for display to the admin
    condensedData = []
    
    for team in tournament.teams:
        status, prettyStatus = tournament.getTeamStatus(team)
        
        condensed = {
            'seed': team.seed,
            'name': team.name,
            'status': {
                'status': status,
                'display': prettyStatus,
            },
            'online': 'Online' if all([p.online > 0 for p in team.players])\
                      else 'Offline'
        }
        
        condensedData.append(condensed)
        
    ajaxData = {
        'data': condensedData
    }
    
    return json.dumps(ajaxData)

#----- SocketIO events -----#
@socketio.on('connect', namespace='/participant')
def user_connect():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    if team.eliminated:
        # This can be handled more gracefully
        abort(404)
    
    # Affect match state
    player.online += 1
    
    # XXX update state, put in listener
    match._updateState()
    
    # Join new room
    session['matchId'] = match.id
    join_room(match.id)
    
    print('Participant {} connected, joined room #{}'
        .format(user.id, match.id))
    
    # This needs to be done in the /chat namespace, so switch it temporarily
    request.namespace = '/chat'
    join_room(match.chat.getRoom())
    request.namespace = '/participant'
    
    lobbyData = match.lobbyData
    # Extra data since we can't send things in the connect event
    emit('handshake', {
            'playerSettings': user.getSettings()
        },
        broadcast=False, include_self=True)
        
    # Tell the user to join their first match too
    emit('join lobby', {
            'lobbyData': lobbyData
        },
        broadcast=False, include_self=True)
        
    # TODO: update match state and post lobby updates to room 
    updatedLobbyData = {}
    updatedLobbyData['teams'] = lobbyData['teams']
    updatedLobbyData['state'] = lobbyData['state']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=False,
            room = match.id, namespace='/participant')
    
@socketio.on('disconnect', namespace='/participant')
def user_disconnect():
    userId = session.get('userId', None)
    tournamentId = session.get('tourneyId', None)
    
    user = um.getUserById(userId)
    
    # User doesn't exist, this shouldn't happen ever
    if user is None:
        raise AssertionError('User disconnected, but didn\'t exist')
        
    tournament = tm.getTournamentById(tournamentId)
    if tournament is None:
        abort(404)
    
    # Tournament doesn't exist
    if tournament is None:
        return
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    # Affect state
    player.online -= 1
    
    if match is not None:
        # XXX update state, put in listener
        match._updateState()
    # Match is none, player was eliminated
    else:
        return
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['teams'] = lobbyData['teams']
    updatedLobbyData['state'] = lobbyData['state']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=False,
            room = match.id)
    
    print('User {} disconnected'.format(user.id))
    
# State reporting from client

# Someone picked their legend
@socketio.on('pick legend', namespace='/participant')
def pick_legend(data):
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    player.currentLegend = data['legendId']
    match._updateState()
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['state'] = lobbyData['state']
    updatedLobbyData['teams'] = lobbyData['teams']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=True,
            room = match.id)
    
    print('User {} selected {}'.format(user.id, data['legendId']))
    
# Someone banned a realm
@socketio.on('ban realm', namespace='/participant')
def ban_realm(data):
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    match.addRealmBan(data['realmId'])
    match._updateState()
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['state'] = lobbyData['state']
    updatedLobbyData['realmBans'] = lobbyData['realmBans']
    updatedLobbyData['currentRealm'] = lobbyData['currentRealm']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=True,
            room = match.id)
    print('Banned {}'.format(data['realmId']))
    
# Someone picked a realm
@socketio.on('pick realm', namespace='/participant')
def pick_realm(data):
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    match.currentRealm = data['realmId']
    match._updateState()
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['state'] = lobbyData['state']
    updatedLobbyData['currentRealm'] = lobbyData['currentRealm']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=True,
            room = match.id)
    print('Picked {}'.format(data['realmId']))

# A room was selected
@socketio.on('set room', namespace='/participant')
def select_room(data):
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    match.roomNumber = data['roomNumber']
    match._updateState()
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['state'] = lobbyData['state']
    updatedLobbyData['roomNumber'] = lobbyData['roomNumber']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=True,
            room = match.id)
    print('Selected room number {}'.format(data['roomNumber']))
    
    
# A team win was reported
@socketio.on('report win', namespace='/participant')
def report_win(data):
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    match.incrementScore(data['teamIndex'])
    
    match._updateState()
    
    lobbyData = match.lobbyData
    updatedLobbyData = {}
    updatedLobbyData['state'] = lobbyData['state']
    updatedLobbyData['teams'] = lobbyData['teams']
    updatedLobbyData['currentRealm'] = lobbyData['currentRealm']
    updatedLobbyData['realmBans'] = lobbyData['realmBans']
    
    emit('update lobby', updatedLobbyData, broadcast=True, include_self=True,
            room = match.id)
    
    if match.winner is not None:
        nextLobbyData = match.nextMatch.lobbyData
        updatedNextLobbyData = {}
        updatedNextLobbyData['state'] = nextLobbyData['state']
        updatedNextLobbyData['teams'] = nextLobbyData['teams']
        emit('update lobby', updatedNextLobbyData, broadcast=True, 
                include_self=False, room = match.nextMatch.id)

# A team win was reported
@socketio.on('advance lobby', namespace='/participant')
def advance_lobby():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    #Tournament doesn't exist
    if tournament is None:
        abort(404)
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    if team.eliminated:
        raise AssertionError('Eliminated player trying to advance match.')
    
    for m in match.prereqMatches:
        if m is None:
            continue
        for t in m.teams:
            # This user's team in a previous match, we want to leave rooms
            # associated with this match
            if t.id == team.id:
                leave_room(m.id)
                
                # This needs to be done in the /chat namespace, so switch it temporarily
                request.namespace = '/chat'
                leave_room(m.chat.getRoom())
                request.namespace = '/participant'
                
                break
        # Continue if we didn't find it
        else:
            continue
        # Break because we found it
        break
    else:
        raise AssertionError('Didn\'t find rooms to leave.')
    
    # Join new match lobby
    join_room(match.id)
    
    # This needs to be done in the /chat namespace, so switch it temporarily
    request.namespace = '/chat'
    join_room(match.chat.getRoom())
    request.namespace = '/participant'
    
    emit('join lobby', {'lobbyData': match.lobbyData},
            broadcast=False, include_self=True, room = match.id)

# A chat message was sent by a client
@socketio.on('send', namespace='/chat')
def chat_send(data):
    tourneyId = session.get('tourneyId', None)
    userId = session.get('userId', None)
    
    # No tourneyId, userId. Could probably be handled more gracefully
    if None in (tourneyId, userId):
        print('Tried to send chat message with bad info. tId: {}, uId: {}'
            .format(tourneyId, userId))
        return
    
    user = um.getUserById(userId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; message rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
        
    sentTime = datetime.datetime.now().isoformat()
    
    chatId = data['chatId']
    message = data['message']
    
    chat = cm.getChat(chatId)
    if not chat:
        return
        
    room = chat.getRoom()
    
    # User not in this chat
    if room not in rooms():
        return
    
    messageData = {'senderId': str(user.id),
                   'avatar': user.avatar,
                   'name': user.username,
                   'message': message,
                   'sentTime': sentTime}
    
    chat.addMessage(messageData)
    # XXX Move this to a listener
    cm._writeChatToDB(chat)
    
    emit('receive', {
        'messageData': messageData,
        'chatId': chatId
    }, broadcast=True, include_self=True, room=room)
    
# A user is requesting a full chat log
@socketio.on('request log', namespace='/chat')
def chat_request_log(data):
    chatId = data['chatId']
    
    chat = cm.getChat(chatId)
    
    # TODO: Maybe handle this a bit more gracefully
    if not chat:
        return
        
    room = chat.getRoom()
    
    # User not in this chat
    if room not in rooms():
        return
    
    emit('receive log', {
        'log': chat.log,
        'chatId': chatId
    }, broadcast=False, include_self=True)
        
def runWebServer(debug=False):
    """
    Run the web server.
    """
    app.debug = debug
    socketio.run(app, host='0.0.0.0')
