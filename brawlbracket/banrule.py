from brawlbracket import util

class BanRule:
    """
    Class that handles ban and pick orders for matches.
    """
    def __init__(self):
        pass
        
    def advanceState(self, match):
        """
        Handles all of the logic of what the next state should be.
        Generic implementation naively checks state name and hands off to a
        sub function.
        
        State order:
            - waitingForPlayers
            - selectLegends
            - selectRealm
            - createRoom
        
        Directly modifies match.state.
        """
        state = match.state
        # Entry point into the cyclic states, straight to selectLegends
        if state['name'] in ['waitingForMatch', 'waitingForPlayers']:
            state.clear()
            state['name'] = 'selectLegends'
        
        while True:
            if state['name'] == 'selectLegends':
                self._getNextLegendStep(match)
            
            if state['name'] == 'selectRealm':
                self._getNextRealmStep(match)
            
            if state['name'] == 'createRoom':
                self._getNextRoomStep(match)
            
            if state['name'] == 'inGame':
                if self._getNextGameStep(match):
                    continue
            break
    
    def _getNextLegendStep(self, match):
        """
        Intended to determine the next step in the legend picking process.
        This could be the next person to pick or ban.
        """
        raise NotImplementedError('No generic getNextLegendStep')
    
    def _getNextRealmStep(self, match):
        """
        Intended to determine the next step in the realm picking process.
        This could be the next person to pick or ban.
        """
        raise NotImplementedError('No generic getNextRealmStep')
    
    def _getNextRoomStep(self, match):
        """
        Intended to determine the next step in the room picking process.
        Generic implementation checks to see if room is set, if it isn't
        then it passes. If it is then it advances to the inGame state.
        """
        if match.roomNumber is not None:
            state = match.state
            state.clear()
            state['name'] = 'inGame'
    
    def _getNextGameStep(self, match):
        """
        Intended to determine the next step in the in game process.
        
        Returns True if the state update process should be restarted.
        """
        state = match.state
        currentScore = match.score
        oldScore = match.oldScore
        
        # Error
        if currentScore < oldScore:
            raise AssertionError('Current score was less than old score: '
                                 '{}, {}'.format(currentScore, oldScore))
        # Nothing to do
        elif currentScore == oldScore:
            return False
        # Game done, update
        else:
            # Match done move forwards
            if max(currentScore) > (match.bestOf // 2):
                self._advanceToNewMatch(match)
                return False
            else:
                self._resetForNewGame(match)
                
                return True
    
    def _resetForNewGame(self, match):
        """
        Intended to reset a match's state such that it is ready to start a new
        game.
        """
        raise NotImplementedError('No generic resetForNewGame')
    
    def _advanceToNewMatch(self, match):
        """
        Intended to clean up this match's final state and then move players
        appropriately to new states.
        """
        raise NotImplementedError('No generic resetForNewGame')

class BasicRules(BanRule):
    """
    A basic implementation of rules.
    """     
    # override
    def _getNextLegendStep(self, match):
        """
        Basic picking order. Higher seed
        """
        state = match.state
        
        teams = list(match.teams)
        teams.sort(key = lambda t: t.seed, reverse = True)
        
        userIds = None
        if any(p.currentLegend is None for p in teams[0].players):
            userIds = [str(p.user.id) for p in teams[0].players
                            if p.currentLegend is None]
        elif any(p.currentLegend is None for p in teams[1].players):
            userIds = [str(p.user.id) for p in teams[1].players
                            if p.currentLegend is None]
        # We're done picking, advance.
        else:
            state.clear()
            match.state['name'] = 'selectRealm'
            return
        
        state.clear()
        state['name'] = 'selectLegends'
        match.state['canPick'] = userIds
    
    def _getNextRealmStep(self, match):
        """
        Basic pick ban order.
        """
        currentBans = match.getRealmBans()
        state = match.state
        # Ban up until 2 realms left
        if len(currentBans) < (len(util.eslRealms) - 2):
            state.clear()
            state['name'] = 'selectRealm'
            
            # Player 0 == captain
            state['turn'] = str(match.teams[len(currentBans)%2]\
                                .players[0].user.id)
            state['action'] = 'ban'
        elif match.currentRealm is None:
            state.clear()
            state['name'] = 'selectRealm'
            
            # Player 0 == captain
            state['turn'] = str(match.teams[len(currentBans)%2]\
                                .players[0].user.id)
            state['action'] = 'pick'
        else:
            state.clear()
            state['name'] = 'createRoom'

class ESLRules(BanRule):
    """
    Rules for ESL style tournaments
    """
            
    # override
    def _getNextLegendStep(self, match):
        """
        Basic picking order. Higher seed picks first.
        
        This is NOT ESL rules yet.
        """
        state = match.state
        
        teams = list(match.teams)
        teams.sort(key = lambda t: t.seed)
        
        userIds = None
        if any(p.currentLegend is None for p in teams[0].players):
            userIds = [str(p.user.id) for p in teams[0].players
                            if p.currentLegend is None]
        elif any(p.currentLegend is None for p in teams[1].players):
            userIds = [str(p.user.id) for p in teams[1].players
                            if p.currentLegend is None]
        # We're done picking, advance.
        else:
            state.clear()
            match.state['name'] = 'selectRealm'
            return
        
        state.clear()
        state['name'] = 'selectLegends'
        match.state['canPick'] = userIds
    
    def _getNextRealmStep(self, match):
        """
        First game players ban until one realm is left. Subsequent games
        higher seed bans two realms and low seed picks from remaining.
        """
        currentBans = match.getRealmBans()
        state = match.state
        gameNumber = sum(match.score)
        
        # First game of match
        if gameNumber == 0:
            # Ban up until one realm left
            if len(currentBans) < (len(util.eslRealms) - 1):
                sortedTeams = sorted(match.teams,
                                     key = lambda t: t.seed,
                                     reverse = True)
                state.clear()
                state['name'] = 'selectRealm'
                state['action'] = 'ban'
                
                # Player 0 == captain
                state['turn'] = str(sortedTeams[len(currentBans)%2]\
                                    .players[0].user.id)
                                    
            # Auto pick the last realm
            else:
                for realm in util.eslRealms:
                    if realm not in currentBans:
                        match.currentRealm = realm
                        break
                else:
                    raise AssertionError('Only one realm left but couldn\'t '
                                         'find it.')
                
                # Advance to next state
                state.clear()
                state['name'] = 'createRoom'
                
        # After first game
        else:
            # Ban up to two realms
            if len(currentBans) < 2:
                highestSeed = max(match.teams, key=lambda t: t.seed)
                
                state.clear()
                state['name'] = 'selectRealm'
                state['action'] = 'ban'
                state['turn'] = str(highestSeed.players[0].user.id)
                state['remaining'] = 2 - len(currentBans)
            # Low seed picks realm
            elif match.currentRealm is None:
                lowestSeed = min(match.teams, key=lambda t: t.seed)
                
                state.clear()
                state['name'] = 'selectRealm'
                state['action'] = 'pick'
                state['turn'] = str(lowestSeed.players[0].user.id)
            # Advance to next state
            else:
                state.clear()
                state['name'] = 'createRoom'
    
    def _resetForNewGame(self, match):
        """
        Intended to reset a match's state such that it is ready to start a new
        game.
        """
        state = match.state
        currentScore = match.score
        oldScore = match.oldScore
        
        loserIndex = 1 if oldScore[0] < currentScore[0] else 0
    
        # Reset things to pregame state
        match.clearRealmBans()
        match.currentRealm = None
        match.oldScore = currentScore.copy()
        
        # Reset loser player legends to None so they can repick
        for player in match.teams[loserIndex].players:
            player.currentLegend = None
        
        state.clear()
        state['name'] = 'selectLegends'
    
    def _advanceToNewMatch(self, match):
        """
        Handles single elim advancement.
        """
        state = match.state
        currentScore = match.score
        oldScore = match.oldScore
        teams = match.teams
        nextMatch = match.nextMatch
        
        
        winners = None
        winnerIndex = None
        losers = None
        if oldScore[0] < currentScore[0]:
            winners = teams[0]
            winnerIndex = 0
            losers = teams[1]
        elif oldScore[1] < currentScore[1]:
            winners = teams[1]
            winnerIndex = 1
            losers = teams[0]
        else:
            raise AssertionError('Advancing to new state without a winner')
        
        match.winner = winners
        losers.eliminated = True
        
        state.clear()
        state['name'] = 'complete'
        state['winnerIndex'] = winnerIndex
        state['finalRound'] = nextMatch is None
        
        if nextMatch is not None:
            for player in winners.players:
                player.currentLegend = None
            nextMatch.setTeam(winners, match.nextMatchSide)
            nextMatch._updateState() # XXX Fix this
            

# List of rulesets
rulesets = {
    'basic': BasicRules(),
    'esl': ESLRules()
}
