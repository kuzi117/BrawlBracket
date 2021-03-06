import json

from flask import session
from flask import redirect
from flask import url_for
from flask import render_template
from flask import abort
from flask import g

from brawlbracket.app import app
from brawlbracket import usermanager as um
from brawlbracket import tournamentmanager as tm

from brawlbracket.viewdecorators import *

print('Registering admin pages routes...')
                           
# Admin dashboard
@app.route('/app-pages/admin-dashboard/<tourneyName>')
@tourney_admin_only
def admin_dashboard():
    if g.user is None:
        return redirect(url_for('tournament_index', tourneyName = g.tourneyName))

    return render_template('app/pages/admin-dashboard.html',
                           tournament=g.tournament,
                           tourneyName=g.tourneyName)
                                                      
# Admin chat (for contacting players/other admins)
@app.route('/app-pages/admin-chat/<tourneyName>')
@tourney_admin_only
def admin_chat():
   if g.user is None:
       return redirect(url_for('tournament_index', tourneyName = g.tourneyName))

   return render_template('app/pages/admin-chat.html',
                          tournament=g.tournament,
                          tourneyName=g.tourneyName)

# Lobby data
@app.route('/app-data/lobbies/<tourneyName>')
@tourney_admin_only
def data_lobbies():
    # Get a condensed list of lobby data for display to the admin
    condensedData = []

    for match in g.tournament.matches:
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
    
# Team data
@app.route('/app-data/teams/<tourneyName>')
@tourney_admin_only
def data_teams():
    # Get a condensed list of user data for display to the admin
    condensedData = []
    
    for team in g.tournament.teams:
        status, prettyStatus = g.tournament.getTeamStatus(team)
        
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
    
# User data
@app.route('/app-data/users/<tourneyName>')
@tourney_admin_only
def data_users():
    # Get a condensed list of user data for display to the admin
    condensedData = []
    
    for team in g.tournament.teams:
        for player in team.players:
            status, prettyStatus = g.tournament.getTeamStatus(team)
            
            condensed = {
                'name': player.user.username,
                'team': team.name,
                'online': 'Online' if player.online else 'Offline',
                'chatId': str(player.adminChat.id if player.adminChat else None)
            }
            
            condensedData.append(condensed)
        
    ajaxData = {
        'data': condensedData
    }
    
    return json.dumps(ajaxData)