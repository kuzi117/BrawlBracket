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
steamIds = [76561198042414835, 76561198078549692, 76561197993702532,
            76561198069178478, 76561198065399638, 76561197995127703,
            76561198068388037, 76561198050490587, 76561198072175457,
            76561198063265824, 76561198042403860]
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
    for i, user in enumerate(tempUsers):
        team = tempTourney.createTeam(i) # i = seed
        player = tempTourney.createPlayer(user)
        team.players.append(player)
    print('Temp tournament has {} users!'.format(len(tempTourney.teams)))
    tempTourney.generateMatches()
    
    tempTourney.admins.add(um.getUserBySteamId(76561198042414835))
    tempTourney.admins.add(um.getUserBySteamId(76561197993702532))
    print('Admins: ', [a.username for a in tempTourney.admins])
    tm._writeTournamentToDB(tempTourney) # DEBUG THIS SHOULDN'T BE LIKE THIS
# End temp tournament generation
    
@app.context_processor
def default_template_data():
    userId = session.get('userId', None)
    user = um.getUserById(userId)
    
    userName = user.username if user else None
    userAvatar = user.avatar if user else None
    
    return dict(versionNumber = __version__,
                userName = userName,
                userAvatar = userAvatar)
                
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
    if session.get('userId', None) is not None:
        return redirect(oid.get_next_url())
    return oid.try_login('http://steamcommunity.com/openid')

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
    
    if userId is None:
        print('No userId; returned to index.')
        return redirect('/')
        
    user = um.getUserById(userId)
        
    if request.method == 'GET':
        return render_template('settings.html',
                               legendData=util.orderedLegends,
                               serverRegions=util.orderedRegions,
                               userSettings=user.getSettings())
                               
    elif request.method == 'PUT':
        if user.setSettings(request.json):
            return json.dumps({'success': True}), 200
            
        else:
            return json.dumps({'success': False}), 500

# Tournament index page
@app.route('/t/<tourneyName>/', methods=['GET', 'POST'])
def tournament_index(tourneyName):
    if not tm.tournamentNameExists(tourneyName):
        abort(404)
    
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('tournament.html',
                           tourneyName=tourneyName,
                           tournament=tournament)

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
                           tourneyFullName=tournament.name,
                           userId=user.id,
                           basePath='/t/{}/app/'.format(tourneyName))

# Contact admin page
@app.route('/app-content/contact-admin/<tourneyName>')
def contact_admin(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('app/content/contact-admin.html',
                           tourneyFullName=tournament.name,
                           tourneyName=tourneyName)
    
# App version of tournament index
@app.route('/app-content/index/<tourneyName>')
def app_tournament_index(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)

    return render_template('app/content/tournament-index.html',
                           tourneyName=tourneyName,
                           tourneyFullName=tournament.name,
                           tournament=tournament)
    
# Lobby content
@app.route('/app-content/lobby/<tourneyName>')
def lobby(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    return render_template('app/content/lobby.html',
                           tourneyFullName=tournament.name,
                           tourneyName=tourneyName)

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
        redirect(url_for('tournament_index'))
    
    print(user, tournament.admins)
    if user not in tournament.admins:
        abort(403)

    return render_template('app/admin-app.html',
                           startPage=startPage,
                           tourneyName=tourneyName,
                           tourneyFullName=tournament.name,
                           userId=user.id,
                           basePath='/t/{}/admin/'.format(tourneyName))
                           
# Admin dashboard
@app.route('/app-content/admin-dashboard/<tourneyName>')
def admin_dashboard(tourneyName):
    tournament = tm.getTournamentByName(tourneyName)
    userId = session.get('userId')
    user = um.getUserById(userId)
    
    if tournament is None:
        abort(404)
    
    if user is None:
        redirect(url_for('tournament_index'))
    
    if user.id not in tournament.admins:
        abort(403)

    return render_template('app/content/admin-dashboard.html',
                           tourneyFullName=tournament.name,
                           tourneyName=tourneyName)
    
#----- Page elements -----#
    
# Connect error
@app.route('/app-content/lobby-error/<tourneyName>')
def lobby_error(tourneyName):
    return render_template('app/content/lobby-error.html')
    
# Legend roster
@app.route('/app-content/roster')
def roster():
    return render_template('app/content/lobby-roster.html',
    legendData=util.orderedLegends)
    
# Map picker
@app.route('/app-content/realms')
def realms():
    return render_template('app/content/lobby-realms.html',
                           realmData=util.orderedRealms)

#----- Raw data -----#

# Lobby data
@app.route('/app-data/lobbies/<tourneyName>')
def data_lobbies(tourneyName):
    tourneyId = tourneys[tourneyName]

    # Get a condensed list of lobby data for display to the admin
    condensedData = []
    
    matches = brawlapi.getTournamentMatches(tourneyId)
    for matchId in matches:
        lobbyData = brawlapi.getLobbyData(tourneyId, matchId)
        participants = lobbyData['participants']
        
        # Assemble score string 
        if len(participants) == 2:
            # If there are less than 2 players, this will be either empty or just show one number
            scoreString = '-'.join([str(pData['wins']) for pData in participants])
        else:
            scoreString = '0-0'
            
        # Add on bestOf value (e.g. best of 3)
        scoreString += ' (Bo{})'.format(lobbyData['bestOf'])
        
        status, prettyStatus, statusOrder = brawlapi.getLobbyStatus(tourneyId, matchId)
        
        condensed = {
            'id': lobbyData['challongeId'],
            'p1Name': participants[0]['name'] if len(participants) > 0 else '',
            'p2Name': participants[1]['name'] if len(participants) > 1 else '',
            'score': scoreString,
            'room': lobbyData['roomNumber'] or '',
            'startTime': lobbyData['startTime'] or '',
            'status': {
                'state': lobbyData['state']['name'],
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
@app.route('/app-data/users/<tourneyName>')
def data_users(tourneyName):
    tourneyId = tourneys[tourneyName]
    
    # Get a condensed list of user data for display to the admin
    condensedData = []
    
    users = brawlapi.getTournamentUsers(tourneyId)
    for user in users:
        status, prettyStatus = brawlapi.getParticipantStatus(tourneyId, user)
        pData = brawlapi.getParticipantData(tourneyId, user.participantId)
        
        condensed = {
            'seed': pData['seed'],
            'name': pData['display-name'],
            'status': {
                'status': status,
                'display': prettyStatus,
            },
            'online': 'Online' if brawlapi.isUserOnline(tourneyId, user) else 'Offline'
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
    tourneyId = session.get('tourneyId', None)
    tournament = tm.getTournamentById(tourneyId)
    
    # Weren't passed a userId
    if userId is None:
        print('User id missing; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    user = um.getUserById(userId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    player.online = True
    
    # Join new room
    session['matchId'] = match.id
    join_room(match.id)
    
    print('Participant {} connected, joined room #{}'
        .format(user.id, match.id))
    
    # This needs to be done in the /chat namespace, so switch it temporarily
    request.namespace = '/chat'
    join_room(match.chat.getRoom())
    request.namespace = '/participant'
        
    emit('join lobby', {
            'lobbyData': match.getLobbyData(),
            'playerSettings': user.getSettings()
        },
        broadcast=False, include_self=True)
        
    # TODO: update match state and post lobby updates to room 
    
@socketio.on('disconnect', namespace='/participant')
def participant_disconnect():
    userId = session.get('userId', None)
    tournamentId = session.get('tourneyId', None)
    
    # Bad info, but they've disconnected anyways...
    if None in (userId, tournamentId):
        return
    
    user = um.getUserById(userId)
    
    # User doesn't exist
    if user is None:
        return
        
    tournament = tm.getTournamentById(tournamentId)
    
    # Tournament doesn't exist
    if tournament is None:
        return
    
    info = tournament.getUserInfo(user)
    
    if info is None:
        # TODO: Issue error saying we somehow got into a tournament that
        # we don't live in
        pass
    
    match, team, player = info
    
    player.online = False
    # TODO: update match state and post lobby updates to room 

    print('User {} disconnected'.format(user.id))
    

# A participant win was reported
@socketio.on('report win', namespace='/participant')
def participant_report_win(data):
    participantId = data['player-id']
    tourneyId = session['tourneyId']
    matchId = brawlapi.getParticipantMatch(tourneyId, participantId)
    
    print('Participant #{} won a game. mID: {}, tId: {}'
        .format(participantId, matchId, tourneyId))
    
    brawlapi.incrementMatchScore(tourneyId, matchId, (1, 0))
    
    lData = brawlapi.getLobbyData(tourneyId, matchId)
    emit('update lobby', lData,
        broadcast=True, include_self=True, room=matchId)

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
    
    user = brawlapi.getUser(tourneyId, userId)
    
    # User doesn't exist
    if user is None:
        print('User doesn\'t exist; connection rejected')
        emit('error', {'code': 'bad-participant'},
            broadcast=False, include_self=True)
        return False
        
    sentTime = datetime.datetime.now().isoformat()
    
    chatId = data['chatId']
    message = data['message']
    
    chat = brawlapi.getChat(tourneyId, chatId)
    if not chat:
        return
        
    room = chat.getRoom()
    
    # User not in this chat
    if room not in rooms():
        return
    
    pData = brawlapi.getParticipantData(tourneyId, user.participantId)
    # This should really never happen, it should have been guaranteed by
    # them connecting
    if pData is None:
        print('Couldn\'t find pData while sending chat. tID: {}, pID: {}'
            .format(tourneyId, user.participantId))
        return
    
    avatarURL = brawlapi.getParticipantAvatar(pData)
    
    messageData = {'senderId': str(user.userId),
                   'avatar': avatarURL,
                   'name': pData['name'],
                   'message': message,
                   'sentTime': sentTime}
    
    chat.addMessage(messageData)
    
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
    socketio.run(app)