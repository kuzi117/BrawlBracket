import uuid
import json

import bidict
import dateutil.parser

from brawlbracket.bracket import tournament as trn
from brawlbracket.bracket import player as plr
from brawlbracket.bracket import team as tem
from brawlbracket.bracket import match as mch
from brawlbracket import usermanager as um
from brawlbracket import chatmanager as cm
from brawlbracket import db_wrapper
from brawlbracket import util

_tournamentsByName = bidict.bidict()
_tournaments = []

_db = None

def createTournament(shortName, **kwargs):
    """
    Creates a tournament.
    shortName: This tournament's unique shortName (string)
    
    Returns the new Tournament.
    Returns None if the shortName wasn't unique.
    """
    if shortName in _tournamentsByName:
        return None
    
    tournament = trn.SingleElimTournament(
        shortName,
        callbacks = (_matchDBCallback, _teamDBCallback, _playerDBCallback),
        fullCallback = _writeTournamentToDB,
        **kwargs)
    tournament._dbCallback = _tournamentDBCallback
    
    _writeTournamentToDB(tournament)
    
    _tournamentsByName[shortName] = tournament.id
    _tournaments.append(tournament)
    
    return tournament
    
def getTournamentById(id):
    """
    Gets a tournament by uuid.
    
    Returns None if no tournament was found.
    Returns the tournament found.
    """
    for tournament in _tournaments:
        if tournament.id == id:
            return tournament
    
    tournament = _getTournamentFromDBById(id)
    if tournament is not None:
        _tournaments.append(tournament)
        _tournamentsByName[tournament.shortName] = tournament.id
        return tournament
    else:
        return None

def getTournamentByName(shortName):
    """
    Gets a tournament by short name.
    
    Returns None if no tournament was found.
    Returns the tournament found.
    """
    id = _tournamentsByName.get(shortName, None)
    if id is not None:
        return getTournamentById(id)
    
    tournament = _getTournamentFromDBByName(shortName)
    if tournament is not None:
        _tournaments.append(tournament)
        _tournamentsByName[tournament.shortName] = tournament.id
        return tournament
    else:
        return None

def tournamentNameExists(shortName):
    """
    Check if a tournament name exists.
    
    shortName: Tournament shortName to check.
    
    Returns True if the shortName is in use, False otherwise.
    """
    # TODO this can be optimized to only check if a tournament exists in the
    # data base not have to reconstruct the entire thing if we haven't already
    return getTournamentByName(shortName) is not None

def _getTournamentFromDBById(id):
    """
    Gets a tournament from the database by id.
    
    Returns the tournament, full formed, if it was in the database and could be
    constructed fully.
    Returns None otherwise.
    """
    if _db is None:
        _initDB()
    
    rows = _db.select_values(
        'tournaments',
        ['*'],
        ['id = \'{}\''.format(id)])
    
    # Die early if no results
    if not rows:
        return None
    else:
        tournamentData = rows[0]
        return _buildTournament(tournamentData)

def _getTournamentFromDBByName(shortName):
    """
    Gets a tournament from the database by short name.
    
    Returns the tournament, full formed, if it was in the database and could be
    constructed fully.
    Returns None otherwise.
    """
    if _db is None:
        _initDB()
    
    rows = _db.select_values(
        'tournaments',
        ['*'],
        ['shortName = \'{}\''.format(shortName)])
    
    # Die early if no results
    if not rows:
        return None
    else:
        tournamentData = rows[0]
        return _buildTournament(tournamentData)

def _buildTournament(tournamentData):
    """
    Builds a tournament from database tournament data.
    """
    #print('Making tournament from: ', tournamentData)
    id = tournamentData[0]
    name = tournamentData[1]
    shortName = tournamentData[2]
    matchIds = tournamentData[3]
    teamIds = tournamentData[4]
    playerIds = tournamentData[5]
    adminIds = tournamentData[6]
    rootId = tournamentData[7]
    startTime = dateutil.parser.parse(tournamentData[8])\
        if tournamentData[8] is not None else None
    checkInTime = dateutil.parser.parse(tournamentData[9])\
        if tournamentData[9] is not None else None
    description = tournamentData[10]
    style = tournamentData[11]
    
    tournament = None
    if style == 'Single Elimination':
        tournament = trn.SingleElimTournament(
            shortName,
            uuid = id,
            name = name,
            startTime = startTime,
            checkInTime = checkInTime,
            description = description
            )
    else:
        raise ValueError('Bad tournament style: {}'.format(style))
    
    # Quick function that returns a string surrounded by quotes
    q = lambda x: '\'{}\''.format(x)
    
    # ---- MAKE ADMINS ----
    admins = set()
    for adminId in adminIds:
        user = um.getUserById(adminId)
        if user is None:
            raise AssertionError('Admin with bad id. {}'.format(adminId))
        admins.add(user)
    
    # ---- MAKE PLAYERS ----
    players = set()
    cond = 'id IN ({})'
    cond = cond.format(','.join(['{}']*len(playerIds))) # Format in format strs
    cond = cond.format(*[q(id) for id in playerIds]) # Format in ids
    playerRows = _db.select_values(
        'players',
        ['*'],
        [cond])
    
    # We should've written all players, how could this happen?
    if len(playerRows) !=  len(playerIds):
        raise AssertionError(
            'Got less players than ids. '
            '{}, {}'.format([r[0] for r in playerRows],
                            [str(id) for id in playerIds]))
    
    for playerData in playerRows:
        #print('Making player from: ', playerData)
        id = playerData[0]
        user = um.getUserById(playerData[1])
        if user is None:
            raise AssertionError('Player user was none.'
                                 '{}'.format(playerData[1]))
        player = plr.Player(user, uuid = id)
        player.currentLegend = playerData[2]
        player.online = 0
        player.adminChat = cm.getChat(playerData[3])
        player._dbCallback = _playerDBCallback # Give db callback
        players.add(player)
    
    # ---- MAKE TEAMS ----
    teams = set()
    cond = 'id IN ({})'
    cond = cond.format(','.join(['{}']*len(teamIds))) # Format in format strs
    cond = cond.format(*[q(id) for id in teamIds]) # Format in ids
    teamRows = _db.select_values(
        'teams',
        ['*'],
        [cond])
        
    # We should've written all teams, how could this happen?
    if len(teamRows) !=  len(teamIds):
        raise AssertionError(
            'Got less teams than ids. '
            '{}, {}'.format([r[0] for r in teamRows],
                            [str(id) for id in teamIds]))
    
    for teamData in teamRows:
        #print('Making team from: ', teamData)
        id = teamData[0]
        seed = teamData[1]
        name = teamData[2]
        teamPlayers = []
        for playerId in teamData[3]:
            for player in players:
                if player.id == playerId:
                    teamPlayers.append(player)
                    break
        eliminated = teamData[4]
        checkedIn = teamData[5]
        team = tem.Team(seed, players = teamPlayers, name = name, uuid = id)
        team.eliminated = eliminated
        team.checkedIn = checkedIn
        team._dbCallback = _teamDBCallback # Give db callback
        teams.add(team)
    
    # ---- MAKE MATCHES ----
    matches = set()
    cond = 'id IN ({})'
    cond = cond.format(','.join(['{}']*len(matchIds))) # Format in format strs
    cond = cond.format(*[q(id) for id in matchIds]) # Format in ids
    matchRows = _db.select_values(
        'matches',
        ['*'],
        [cond])
    
    for matchData in matchRows:
        # Trigger warning... trying to assign all of the fields to a useful name
        #print('Making match from: ', matchData)
        id = matchData[0]
        nextMatchSide = matchData[2]
        round = matchData[3]
        number = matchData[4]
        chat = cm.getChat(matchData[6])
        score = json.loads(matchData[7])
        matchTeams = []
        for teamId in matchData[8]:
            if teamId == None:
                matchTeams.append(None)
                continue
            for team in teams:
                if team.id == teamId:
                    matchTeams.append(team)
                    break
        realmBans = json.loads(matchData[9])
        startTime = dateutil.parser.parse(matchData[10])\
                        if matchData[10] is not None else None
        roomNumber = matchData[11]
        currentRealm = matchData[12]
        banRule = matchData[13] # TODO: ACTUALLY CREATE A BAN RULE HERE
        winner = None
        if matchData[14] is not None:
            for team in teams:
                if team.id == matchData[14]:
                    winner = team
                    break
        bestOf = matchData[15]
        state = json.loads(matchData[16])
        
        # Create the match
        match = mch.Match(teams = matchTeams, uuid = id, chat = chat)
        match.nextMatchSide = nextMatchSide
        match.round = round
        match.number = number
        match.score = score
        match.oldScore = score.copy() # Copy so changes don't affect
        match._realmBans = realmBans
        match.startTime = startTime
        match.roomNumber = roomNumber
        match.currentRealm = currentRealm
        match.banRule = banRule
        match.winner = winner
        match.bestOf = bestOf
        match.state = state
        matches.add(match)
    
    # Link tournament structure together in matches
    for match in matches:
        if match.id == rootId:
            tournament._root = match
        
        for matchData in matchRows:
            if matchData[0] != match.id:
                continue
            
            for oMatch in matches:
                if oMatch.id == matchData[1]:
                    match.nextMatch = oMatch
                    continue
                
                if oMatch.id == matchData[5][0]:
                    match.prereqMatches[0] = oMatch
                elif oMatch.id == matchData[5][1]:
                    match.prereqMatches[1] = oMatch
            
            # The break condition is sort of complicated but essentially boils
            # down to: if we have something to set and it's set we're done
            if (matchData[1] is None or match.nextMatch is not None) and\
               (matchData[5][0] is None or
                    match.prereqMatches[0] is not None) and\
               (matchData[5][1] is None or
                    match.prereqMatches[1] is not None):
                        break
        else:
            raise AssertionError('Couldn\'t set up match hierarchy. ({})'
                                    .format(matchData[0]))
                                    
    # Now that we're done setting up matches we can give them their callback
    for match in matches:
        match._dbCallback = _matchDBCallback
        
    tournament.admins = admins
    tournament.players = players
    tournament.teams = teams
    tournament.matches = matches
    
    # Now that we're done setting up tournament we can give it its callbacks
    tournament._dbCallback = _tournamentDBCallback
    tournament._callbacks = (_matchDBCallback, _teamDBCallback, _playerDBCallback)
    tournament._fullCallback = _writeTournamentToDB
    
    return tournament
    
def _constructTournamentDataForDB(tournament):
    """
    Builds a tuple of data from a tournament in the format expected for the
    database.
    """
    tournamentData = (
        tournament.id,
        tournament.name,
        tournament.shortName,
        json.dumps([str(m.id) for m in tournament.matches]),
        json.dumps([str(t.id) for t in tournament.teams]),
        json.dumps([str(p.id) for p in tournament.players]),
        json.dumps([str(a.id) for a in tournament.admins]),
        tournament._root.id if tournament._root is not None else None,
        tournament.startTime.isoformat()\
            if tournament.startTime is not None else None,
        tournament.checkInTime.isoformat()\
            if tournament.checkInTime is not None else None,
        tournament.description,
        tournament.style
    )
    return tournamentData

def _constructMatchDataForDB(match):
    """
    Builds a tuple of data from a match in the format expected for the database.
    """
    matchData = (
        match.id,
        # nextMatch could be None
        match.nextMatch.id\
            if match.nextMatch is not None else None,
        match.nextMatchSide\
            if match.nextMatchSide is not None else None,
        match.round,
        match.number,
        # m could be None
        json.dumps([str(m.id) if m is not None else None
                      for m in match.prereqMatches]),
        match.chat.id,
        json.dumps(match.score),
        # t could be None
        json.dumps([str(t.id) if t is not None else None
                      for t in match.teams]),
        json.dumps(match._realmBans),
        match.startTime.isoformat()\
            if match.startTime is not None else None,
        match.roomNumber if match.bestOf is not None else None,
        match.currentRealm,
        match.banRule,
        match.winner.id\
            if match.winner is not None else None,
        match.bestOf if match.bestOf is not None else None,
        json.dumps(match.state)
    )
    return matchData
    
def _constructTeamDataForDB(team):
    """
    Builds a tuple of data from a team in the format expected for the database.
    """
    teamData = (
        team.id,
        team.seed,
        team.name,
        json.dumps([str(p.id) for p in team.players]),
        team.eliminated,
        team.checkedIn
    )
    return teamData

def _constructPlayerDataForDB(player):
    """
    Builds a tuple of data from a player in the format expected for the database.
    """
    playerData = (
        player.id,
        player.user.id,
        player.currentLegend,
        player.adminChat.id if player.adminChat else None
    )
    return playerData

def _tournamentDBCallback(tournament):
    """
    Write a single tournament to the database.
    Intended as a call back for when a tournament changes internally and needs to 
    write out.
    """
    if _db is None:
        _initDB()
    
    tournamentData = _constructTournamentDataForDB(tournament)
    _db.insert_values('tournaments', [tournamentData])

def _matchDBCallback(match):
    """
    Write a single match to the database.
    Intended as a call back for when a match changes internally and needs to 
    write out.
    """
    if _db is None:
        _initDB()
    
    matchData = _constructMatchDataForDB(match)
    _db.insert_values('matches', [matchData])
    
def _teamDBCallback(team):
    """
    Write a single team to the database.
    Intended as a call back for when a team changes internally and needs to 
    write out.
    """
    if _db is None:
        _initDB()
    
    teamData = _constructTeamDataForDB(team)
    _db.insert_values('teams', [teamData])

def _playerDBCallback(player):
    """
    Write a single player to the database.
    Intended as a call back for when a player changes internally and needs to 
    write out.
    """
    if _db is None:
        _initDB()
    
    playerData = _constructPlayerDataForDB(player)
    _db.insert_values('players', [playerData])

def _writeTournamentToDB(tournament):
    """
    Serializes a tournament, its matches, teams, and players and then inserts 
    them into their own tables in the database.
    """
    if _db is None:
        _initDB()
        
    tournamentData = _constructTournamentDataForDB(tournament)
    print('Writing tournament with: ', tournamentData)
    _db.insert_values('tournaments', [tournamentData])
    
    matchDatas = []
    for match in tournament.matches:
        matchData = _constructMatchDataForDB(match)
        print('Writing match with: ', matchData)
        matchDatas.append(matchData)
    # Only write if there's something to write
    if matchDatas:
        _db.insert_values('matches', matchDatas)
    
    teamDatas = []
    for team in tournament.teams:
        teamData = _constructTeamDataForDB(team)
        print('Writing team with: ', teamData)
        teamDatas.append(teamData)
    # Only write if there's something to write
    if teamDatas:
        _db.insert_values('teams', teamDatas)
    
    playerDatas = []
    for player in tournament.players:
        playerData = _constructPlayerDataForDB(player)
        print('Writing player with: ', playerData)
        playerDatas.append(playerData)
    # Only write if there's something to write
    if playerDatas:
        _db.insert_values('players', playerDatas)
    
def _initDB():
    print('----INIT TOURNAMENT DATABASE----')
    # Need to global because _db is not local to this context
    global _db
    _db = db_wrapper.DBWrapper(util.dbName, filepath=util.dbPath)
    
    # Make tournaments table
    if not _db.table_exists('tournaments'):
        fieldNames = [
            'id',
            'name',
            'shortName',
            'matches',
            'teams',
            'players',
            'admins',
            'root',
            'startTime',
            'checkInTime',
            'description',
            'style'
        ]
        fieldTypes = [
            'UUID',
            'TEXT',
            'TEXT',
            'UUIDLIST',
            'UUIDLIST',
            'UUIDLIST',
            'UUIDLIST',
            'UUID',
            'TEXT',
            'TEXT',
            'TEXT',
            'TEXT'
        ]
        _db.create_table('tournaments', fieldNames, fieldTypes, 'id')
    
    # Make matches table
    if not _db.table_exists('matches'):
        fieldNames = [
            'id',
            'nextMatch',
            'nextMatchSide',
            'round',
            'number',
            'prereqMatches',
            'chat',
            'score',
            'teams',
            'realmBans',
            'startTime',
            'roomNumber',
            'currentRealm',
            'banRule',
            'winner',
            'bestOf',
            'state'
        ]
        fieldTypes = [
            'UUID',
            'UUID',
            'INTEGER',
            'INTEGER',
            'INTEGER',
            'UUIDLIST',
            'UUID',
            'TEXT',
            'UUIDLIST',
            'TEXT',
            'TEXT',
            'INTEGER',
            'TEXT',
            'TEXT',
            'UUID',
            'INTEGER',
            'TEXT'
        ]
        _db.create_table('matches', fieldNames, fieldTypes, 'id')
    
    # Make teams table
    if not _db.table_exists('teams'):
        fieldNames = [
            'id',
            'seed',
            'name',
            'players',
            'eliminated',
            'checkedIn'
        ]
        fieldTypes = [
            'UUID',
            'INTEGER',
            'TEXT',
            'UUIDLIST',
            'BOOLEAN',
            'BOOLEAN'
        ]
        _db.create_table('teams', fieldNames, fieldTypes, 'id')
        
    # Make players table
    if not _db.table_exists('players'):
        fieldNames = [
            'id',
            'user',
            'currentLegend',
            'adminChat'
        ]
        fieldTypes = [
            'UUID',
            'UUID',
            'TEXT',
            'UUID'
        ]
        _db.create_table('players', fieldNames, fieldTypes, 'id')
    
