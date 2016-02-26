import math
from collections import deque

class Match():
    """
    A match between two Teams in the tournament. The Tournament class will create these for you as necessary.
    """
    
    # When printing a match tree, this is the maximum length (in chars) of a seed.
    printSeedLen = 2

    def __init__(self, prereqMatches = None, teams = None, winnerSide = None):
        # The next match
        self.nextMatch = None
    
        # The match round (inverse of depth in the graph, essentially)
        self.round = 0
        
        # The prerequisite matches
        if prereqMatches:
            if len(prereqMatches) != 2:
                raise ValueError('Matches must have 2 prerequisites')
            
            self.prereqMatches = prereqMatches
            
            for match in self.prereqMatches:
                if match is None:
                    continue
                    
                match.nextMatch = self
            
        else:
            self.prereqMatches = [None, None]
        
        # The teams in this match
        if teams:
            if len(teams) != 2:
                raise ValueError('Matches must have 2 teams')
            
            self.teams = [None, None]
            for i, team in enumerate(teams):
                # No team, so try to get the previous match's winner
                if team is None:
                    self._updateTeamFromPrereq(i)
                
                else:
                    self.teams[i] = team
            
        else:
            # Take winners from previous matches
            self._updateTeamsFromPrereqs()
        
        # Winning team
        if winnerSide is None:
            self.winner = None
            
        else:
            self.winner = self.teams[winnerSide]
            
    def _updateTeamsFromPrereqs(self):
        """
        Update all teams based on the prerequisite matches' winners.
        """
        self.teams = [(match.winner if match else None) for match in self.prereqMatches]
        
    def _updateTeamFromPrereq(self, side):
        """
        Update a side's team based on the prerequisite match's winners.
        """
        if self.prereqMatches[side]:
            self.teams[side] = self.prereqMatches[side].winner
        else:
            self.teams[side] = None
        
    def _getTreeDepth(self):
        """
        Get the maximum depth of the match tree.
        """
        return max([(match._getTreeDepth() if match else 0) for match in self.prereqMatches]) + 1

    def _getDisplayLines(self):
        """
        Get the lines which, if printed in sequence, make up the graphical representation
        of this node and its children.
        """
        pnSpaces = 2 ** self.round - 1
        nSpaces = 2 ** (self.round + 1) - 1
        
        # Length of an empty seed
        seedSpace = ' ' * Match.printSeedLen
        
        aLines = self._getChildDisplayLines(0)
        bLines = self._getChildDisplayLines(1)
        
        # Combine previous lines vertically, adding a space between them
        combined = aLines + [''] + bLines
        
        # Pad line lengths
        childLen = max(len(line) for line in combined)
        for i in range(len(combined)):
            combined[i] = ('{:<' + str(childLen) + '}').format(combined[i])
        
        # Add team seeds and corners
        seeds = []
        seedFormat = '{:<' + str(Match.printSeedLen) + '}'
        for team in self.teams:
            if team:
                seeds.append(seedFormat.format(team.seed))
                
            else:
                seeds.append(seedSpace)
        
        combined[pnSpaces] += seeds[0] + '─┐'
        combined[-pnSpaces - 1] += seeds[1] + '─┘'
        
        for i in range(pnSpaces + 1, len(combined) - pnSpaces - 1):
            # Connector for center piece
            if i == nSpaces:
                combined[i] += seedSpace + ' ├─'
                
            # Connecting bars for every other line between corners
            else:
                combined[i] += seedSpace + ' │'
        
        return combined
        
    def _getChildDisplayLines(self, side):
        """
        Get a child node's lines, including extra padding to line up leaf nodes.
        """
        if self.prereqMatches[side]:
            # Get match lines
            lines = self.prereqMatches[side]._getDisplayLines()
            
            return lines
            
        elif self.round > 0:
            # Each match is 6 characters wide plus seed length
            hSpace = 5 * self.round
            
            # Leaf nodes are 3 wide, and this grows exponentially
            vSpace = 2 ** self.round + 1
            
            return [' ' * hSpace] * vSpace
            
        else:
            return ['']
            
    def _destroy(self):
        """
        Unlink the match from other matches.
        """
        if self.nextMatch:
            nextPrereqs = self.nextMatch.prereqMatches
            side = nextPrereqs.index(self)
            nextPrereqs[side] = None
            
        for match in self.prereqMatches:
            if match is None:
                continue
            
            match.nextMatch = None
        
    def __repr__(self):
        return '\n'.join(self._getDisplayLines())

class Team():
    """
    A seeded entry in the tournament. Create these through the Tournament class.
    """
    def __init__(self, seed):
        # The seed
        self.seed = seed
        
    def __repr__(self):
        return str(self.seed)

class Tournament():
    """
    Contains all the data for a tournament. Is responsible for creation of Matches, Teams, and any other
    classes tied to a specific tournament. Also contains convenience functions for updating and getting data.
    """
    def __init__(self, teamCount = 0):
        # Set of all matches. This should only be read by outside classes.
        self.matches = set()
        
        # Set of all teams. This should only be read by outside classes.
        self.teams = set()
        
        for i in range(teamCount):
            self.createTeam(i + 1)
        
        self._generate()
        
    def createTeam(self, *args):
        """
        Create a team and add it to the tournament.
        """
        team = Team(*args)
        self.teams.add(team)
        
        return team
        
    def _removeTeam(self, team):
        """
        Remove a team from the tournament.
        """
        if team not in self.teams:
            raise ValueError('Team not in tournament')
            
        self.teams.remove(team)
        
    def _createMatch(self, *args, **kwargs):
        """
        Create a match and add it to the tournament.
        """
        if len(args) > 0 and args[0]:
            for match in args[0]:
                if match is None: continue
                if match not in self.matches:
                    raise ValueError('Match not in tournament')
                    
        if len(args) > 1 and args[1]:
            for team in args[1]:
                if team is None: continue
                if team not in self.teams:
                    raise ValueError('Team not in tournament')
        
        match = Match(*args, **kwargs)
        self.matches.add(match)
        
        return match
            
    def _generate(self):
        """
        Generate a tournament fitting the number of existing teams.
        """
        return
        
class TreeTournament(Tournament):
    """
    A tournament that follows a tree structure (with each match leading into the next).
    """
    def __init__(self, *args, **kwargs):
        # Root match
        self._root = None
        
        super().__init__(*args, **kwargs)
        
    def _updateMatchRounds(self, match = None, maxDepth = None, depth = 0):
        """
        Determine the rounds for each match.
        """
        if match is None:
            if self._root is None:
                return
                
            match = self._root
        
        if maxDepth is None:
            # Subtract 1 to 0-index rounds
            maxDepth = match._getTreeDepth() - 1
            
        match.round = maxDepth - depth
        
        for prereq in match.prereqMatches:
            if prereq is None:
                continue
        
            self._updateMatchRounds(prereq, maxDepth, depth + 1)
            
    def _generate(self):
        super()._generate()
        
        self._updateMatchRounds()
            
    def __repr__(self):
        return str(self._root)
        
class GenericTreeTournament(TreeTournament):
    """
    A tree tournament with match creation exposed.
    """
    def createMatch(self, *args, **kwargs):
        """
        Create a match and add it to the tournament.
        The last match created is always assumed to be the root.
        """
        self._root = self._createMatch(*args, **kwargs)
        self._updateMatchRounds()
        
        return self._root
        
class SingleElimTournament(TreeTournament):
    """
    A single elimintation tournament.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def _generate(self):
        n = len(self.teams)
        
        if (n < 2):
            return
        
        logN = math.log(n, 2)
        floorLog = math.floor(logN)
        ceilLog = math.ceil(logN)
        
        # Nearest powers of two
        lowPo2 = 2 ** floorLog
        highPo2 = 2 ** ceilLog
        
        # Generate symmetric tree
        roundMatches = []
        self._root = self._genMatchTree(ceilLog, roundMatches)
        firstMatches = roundMatches[0]
        
        # Number of byes needed
        numByes = min(n - lowPo2, highPo2 - n)
        
        # Number of pairs to include in first round
        # This formula is ugly, but it replicates the pattern you can see in these charts:
        # http://www.printyourbrackets.com/single-elimination-tournament-brackets.html
        numFirstRoundPairs = (n - 1 - lowPo2) % (2 ** math.floor(math.log(n - 1, 2))) + 1
        
        # Number of pairs that will skip the first round
        # Byes are only 1 player, and pairs are 2. Divide by 2 to get remaining pairs
        numSkipPairs = (n - numByes - numFirstRoundPairs * 2) / 2
        assert numSkipPairs == math.floor(numSkipPairs), 'Pairs to skip first round must be a whole number'
        numSkipPairs = math.floor(numSkipPairs)
        
        # List of teams that haven't been assigned
        teamsToAssign = list(self.teams)
        teamsToAssign.sort(key=lambda team: team.seed)
        
        # Select the teams to assign in each category
        # Byes are given to highest-seed players, as they get the biggest advantage
        byes = deque(teamsToAssign[:numByes])
        
        # Skipping pairs go to next highest seeds
        skippers = deque(teamsToAssign[numByes:numByes + numSkipPairs * 2])
        
        # Create pairs of skippers, matching highest against lowest seed
        skipPairs = []
        while skippers:
            skipPairs.append((skippers.popleft(), skippers.pop()))
        
        # Remainder stay in first round
        firstRounders = deque(teamsToAssign[numByes + numSkipPairs * 2:])
        
        # Create pairs of first rounders, matching highest against lowest seed
        firstRoundPairs = []
        while firstRounders:
            firstRoundPairs.append((firstRounders.popleft(), firstRounders.pop()))
        
        # Fill in first round with matches
        # This loop interleaves byes, first round pairs, and skipper pairs so that:
        # - first round pairs may match each other
        # - byes are matched against the winner of a first round pair
        # - skip pair winners will be matched against the winner of a bye/first rounder
        i = 0
        while i < len(firstMatches) and len(teamsToAssign) > 0:
            # Do we have any byes left? If so, add one
            if byes:
                match = firstMatches[i]
                match.nextMatch.teams = [byes.popleft(), None]
                
                # This match will be skipped
                self._removeMatch(match)
                
                i += 1
            
            # Do we have any pairs skipping the first round? If so, add them both
            if firstRoundPairs:
                match = firstMatches[i]
                match.teams = list(firstRoundPairs.pop())
                
                i += 1
                
            # If we have room, add a pair that skips the first round.
            if skipPairs:
                match = firstMatches[i]
                match.nextMatch.teams = list(skipPairs.pop())
                
                # These matches will both be skipped
                self._removeMatch(match)
                self._removeMatch(firstMatches[i + 1])
                
                # Two matches have been skipped, so advance by 2
                i += 2
        
        # Set the actual round number for each match
        self._updateMatchRounds()
        
    def _genMatchTree(self, rounds, roundMatches, maxRounds = None):
        """
        Generate a symmetric match tree with the given number of rounds (2^rounds matches).
        """
        # First call, so set the max rounds
        if maxRounds is None:
            maxRounds = rounds
            
            # Create an empty list of matches for each of the rounds
            for i in range(rounds):
                roundMatches.append([])
        
        # First round has no children
        if rounds == 1:
            match = self._createMatch()

        # Recurse to next round
        else:
            match = self._createMatch([
                self._genMatchTree(rounds - 1, roundMatches, maxRounds),
                self._genMatchTree(rounds - 1, roundMatches, maxRounds)
            ])
        
        # Add this match to the list of matches in the current round
        roundMatches[rounds - 1].append(match)
        
        return match