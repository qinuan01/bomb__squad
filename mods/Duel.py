# coding=utf-8
from datetime import datetime
import bsInternal
import bs
import bsBomb
import bsUtils
import random
import math
import time
def bsGetAPIVersion():
    # see bombsquadgame.com/apichanges
    return 4

def bsGetGames():
    return [DuelGame]


class Icon(bs.Actor):

    def __init__(self,player,position,scale,showLives=True,showDeath=True,
                 nameScale=1.0,nameMaxWidth=115.0,flatness=1.0,shadow=1.0):
        bs.Actor.__init__(self)

        self._player = player
        self._showLives = showLives
        self._showDeath = showDeath
        self._nameScale = nameScale

        self._outlineTex = bs.getTexture('characterIconMask')

        icon = player.getIcon()
        self.node = bs.newNode('image',
                               owner=self,
                               attrs={'texture':icon['texture'],
                                      'tintTexture':icon['tintTexture'],
                                      'tintColor':icon['tintColor'],
                                      'vrDepth':400,
                                      'tint2Color':icon['tint2Color'],
                                      'maskTexture':self._outlineTex,
                                      'opacity':1.0,
                                      'absoluteScale':True,
                                      'attach':'bottomCenter'})

        self._nameText = bs.newNode('text',
                                    owner=self.node,

                                    attrs={'text':bs.Lstr(value=player.getName()),
                                           'color':bs.getSafeColor(player.getTeam().color),
                                           'hAlign':'center',
                                           'vAlign':'center',
                                           'vrDepth':410,
                                           'maxWidth':nameMaxWidth,
                                           'shadow':shadow,
                                           'flatness':flatness,
                                           'hAttach':'center',
                                           'vAttach':'bottom'})
        if self._showLives:
            self._livesText = bs.newNode('text',
                                         owner=self.node,
                                         attrs={'text':'x0',
                                                'color':(1,1,0.5),
                                                'hAlign':'left',
                                                'vrDepth':430,
                                                'shadow':1.0,
                                                'flatness':1.0,
                                                'hAttach':'center',
                                                'vAttach':'bottom'})
        self.setPositionAndScale(position,scale)

    def setPositionAndScale(self,position,scale):
        self.node.position = position
        self.node.scale = [70.0*scale]
        self._nameText.position = (position[0],position[1]+scale*52.0)
        self._nameText.scale = 1.0*scale*self._nameScale
        if self._showLives:
            self._livesText.position = (position[0]+scale*10.0,position[1]-scale*43.0)
            self._livesText.scale = 1.0*scale

    def handlePlayerSpawned(self):
        if not self.node.exists(): return
        self.node.opacity = 1.0
        self.setPositionAndScale(self.node.position, 1.0)
        #self.updateForLives()
        self._showDeath = True

    def handlePlayerDied(self):
        if not self.node.exists(): return
        if self._showDeath:
            bs.animate(self.node,'opacity',{0:1.0,50:0.0,100:1.0,150:0.0,200:1.0,250:0.0,
                                            300:1.0,350:0.0,400:1.0,450:0.0,500:1.0,550:0.2,600:1.0})
            self.setPositionAndScale(self.node.position, 0.5)
        self._showDeath = False


class DuelGame(bs.TeamGameActivity):

    @classmethod
    def getName(cls):
        return '单挑'

    @classmethod
    def getScoreInfo(cls):
        return {'scoreName':'Survived',
                'scoreType':'seconds',
                'noneIsWinner':True}

    @classmethod
    def getDescription(cls,sessionType):
        return '在1v1战斗中击败你的敌人。'

    @classmethod
    def supportsSessionType(cls,sessionType):
        return True if (issubclass(sessionType,bs.TeamsSession)
                        or issubclass(sessionType,bs.FreeForAllSession)) else False

    @classmethod
    def getSupportedMaps(cls,sessionType):
        return bs.getMapsSupportingPlayType("melee")

    @classmethod
    def getSettings(cls,sessionType):
        settings = [("Time Limit",{'choices':[('None',0),('1 Minute',60),
                                            ('2 Minutes',120),('3 Minutes',180),('5 Minutes',300),
                                            ('10 Minutes',600),('20 Minutes',1200)],'default':0}),
                    ("Epic Mode",{'default':False}),
                    ("Respawn Powerups When Fights Finish",{'default':True}),
                    ("Keep Powerups Alive When Fighting",{'default':True}),
                    ("Preserve queue through games",{'default':True}),
                    ("Reduce score on suicide",{'default':False}),
                    ("Allow negative score",{'default':False})]
        if issubclass(sessionType, bs.FreeForAllSession):
            settings.append(("Kills to Win Per Player",{'minValue':1,'default':10,'increment':1}))
        else:
            settings.append(("Kills to Win Per Team",{'minValue':1,'default':20,'increment':1}))
        return settings

    def __init__(self,settings):
        bs.TeamGameActivity.__init__(self,settings)
        if self.settings['Epic Mode']: self._isSlowMotion = True

        # show messages when players die since it's meaningful here
        self.announcePlayerDeaths = True

        if isinstance(self.getSession(), bs.FreeForAllSession):
            self.gameData = {}
        self._swipsound = bs.getSound("swip")
        self._scoreBoard = bs.ScoreBoard()

    def getInstanceDescription(self):
        return ('在1v1战斗中击败${ARG1}个敌人', self.settings['Kills to Win Per Player'] if isinstance(self.getSession(), bs.FreeForAllSession) else self.settings['Kills to Win Per Team'])

    def getInstanceScoreBoardDescription(self):
        return ('在1v1战斗中击败${ARG1}个敌人', self.settings['Kills to Win Per Player'] if isinstance(self.getSession(), bs.FreeForAllSession) else self.settings['Kills to Win Per Team'])

    def onTransitionIn(self):
        bs.TeamGameActivity.onTransitionIn(self, music='Epic' if self.settings['Epic Mode'] else 'Survival')
        self._startGameTime = bs.getGameTime()

    def onTeamJoin(self,team):
        if not isinstance(self.getSession(),bs.FreeForAllSession):
            team.gameData['spawnOrder'] = []
        team.gameData['score'] = 0
        if self.hasBegun(): self._scoreBoard.setTeamValue(team,0,self._scoreToWin)

    def onPlayerJoin(self, player):
        player.gameData['icon'] = None
        player.gameData['alive'] = False

        # dont waste time doing this until begin
        if self.hasBegun():
            self._addPlayerToSpawnQueue(player)
            if isinstance(self.getSession(),bs.FreeForAllSession):
                self._addIcon(len(self.gameData['spawnOrder']) - 1,player)
                if len(self.gameData['spawnOrder']) <= 2:
                    self.spawnPlayer(player)
                if len(self.gameData['spawnOrder']) == 2:
                    self._standardDropPowerups()
            else:
                self._addIcon(len(player.getTeam().gameData['spawnOrder']) - 1,player)
                if len(player.getTeam().gameData['spawnOrder']) == 1:
                    self.spawnPlayer(player)
                if (player.getTeam() == self.teams[0] and len(self.teams[0].gameData['spawnOrder']) == 1 and len(self.teams[1].gameData['spawnOrder']) > 0) or (player.getTeam() == self.teams[1] and len(self.teams[1].gameData['spawnOrder']) == 1 and len(self.teams[0].gameData['spawnOrder']) > 0):
                    self._standardDropPowerups()

    def _addPlayersToSpawnQueue(self):
        if self.settings['Preserve queue through games']:
            if isinstance(self.getSession(),bs.FreeForAllSession):
                queuePlayers = []
                newPlayers = []
                sessionQueuePlayers = {}
                maxQueuePosition = -1
                for player in self.players:
                    if player.sessionData.has_key('spawnOrderPosition'):
                        position = player.sessionData['spawnOrderPosition']
                        if sessionQueuePlayers.has_key(position):
                            newPlayers.append(player)
                        else:
                            maxQueuePosition = max(maxQueuePosition, position)
                            sessionQueuePlayers[position] = player
                    else:
                        newPlayers.append(player)
                for i in range(maxQueuePosition + 1):
                    if sessionQueuePlayers.has_key(i):
                        queuePlayers.append(sessionQueuePlayers[i])
                queuePlayers += newPlayers
                for player in queuePlayers:
                    self._addPlayerToSpawnQueue(player)
            else:
                for team in self.teams:
                    queuePlayers = []
                    newPlayers = []
                    sessionQueuePlayers = {}
                    maxQueuePosition = -1
                    for player in team.players:
                        if player.sessionData.has_key('spawnOrderPosition'):
                            position = player.sessionData['spawnOrderPosition']
                            if sessionQueuePlayers.has_key(position):
                                newPlayers.append(player)
                            else:
                                maxQueuePosition = max(maxQueuePosition, position)
                                sessionQueuePlayers[position] = player
                        else:
                            newPlayers.append(player)
                    for i in range(maxQueuePosition + 1):
                        if sessionQueuePlayers.has_key(i):
                            queuePlayers.append(sessionQueuePlayers[i])
                    queuePlayers += newPlayers
                    for player in queuePlayers:
                        self._addPlayerToSpawnQueue(player)
        else:
            if isinstance(self.getSession(),bs.FreeForAllSession):
                for player in self.players:
                    self._addPlayerToSpawnQueue(player)
            else:
                for team in self.teams:
                    for player in team.players:
                        self._addPlayerToSpawnQueue(player)

    def _addPlayerToSpawnQueue(self, player):
        if isinstance(self.getSession(),bs.FreeForAllSession):
            self.gameData['spawnOrder'].append(player)
        else:
            player.getTeam().gameData['spawnOrder'].append(player)

    def _spawnPlayers(self):

        if isinstance(self.getSession(),bs.FreeForAllSession):
            for i,player in enumerate(self.players):
                if i == 2:
                    break
                self.spawnPlayer(self.gameData['spawnOrder'][i])
        else:
            for team in self.teams:
                if len(team.gameData['spawnOrder']) > 0:
                    self.spawnPlayer(team.gameData['spawnOrder'][0])
        self._tryDropPowerups()

    def _addIcons(self):
        # in free-for-all mode, everyone is just lined up along the bottom
        if isinstance(self.getSession(),bs.FreeForAllSession):
            for i,player in enumerate(self.gameData['spawnOrder']):
                self._addIcon(i,player)
        else:
            for team in self.teams:
                for i,player in enumerate(team.gameData['spawnOrder']):
                    self._addIcon(i,player)

    def _addIcon(self, location, player):
        if isinstance(self.getSession(),bs.FreeForAllSession):
            team = player.getTeam()
            if location == 0:
                x = -60
                xOffs = -78
            else:
                x = 60
                xOffs = 78
            isFirst = True if location == 0 or location == 1 else False
            x += xOffs * ((0.8 if location > 1 else 0) + max(location - 2, 0) * 0.56)

            player.gameData['icon'] = Icon(player,
                                           position=(x,(40 if isFirst else 25)),
                                           scale=1.0 if isFirst else 0.5,
                                           nameMaxWidth=130 if isFirst else 75,
                                           nameScale=0.8 if isFirst else 1.0,
                                           flatness=0.0 if isFirst else 1.0,
                                           shadow=0.5 if isFirst else 1.0,
                                           showDeath=False,
                                           showLives=False)
        # in teams mode we split up teams
        else:
            team = player.getTeam()
            if team.getID() == 0:
                x = -60
                xOffs = -78
            else:
                x = 60
                xOffs = 78
            isFirst = True if location == 0 else False
            x += xOffs * ((0.8 if location > 0 else 0) + max(location - 1, 0) * 0.56)

            player.gameData['icon'] = Icon(player,
                                           position=(x,(40 if isFirst else 25)),
                                           scale=1.0 if isFirst else 0.5,
                                           nameMaxWidth=130 if isFirst else 75,
                                           nameScale=0.8 if isFirst else 1.0,
                                           flatness=0.0 if isFirst else 1.0,
                                           shadow=0.5 if isFirst else 1.0,
                                           showDeath=False,
                                           showLives=False)

    def _rearrangeIcons(self, deadPlayer):
        if isinstance(self.getSession(),bs.FreeForAllSession):
            x1 = -60
            xOffs1 = -78

            x2 = 60
            xOffs2 = 78
            for i,player in enumerate(self.gameData['spawnOrder']):
                if i == 0:
                    player.gameData['icon'].setPositionAndScale((x1 + xOffs1 * (0 + max(i - 1, 0) * 0.56),(40 if i == 0 else 25)), 0.5)
                else:
                    player.gameData['icon'].setPositionAndScale((x2 + xOffs2 * ((0.8 if i > 1 else 0) + max(i - 2, 0) * 0.56),(40 if i == 1 else 25)), 1 if i == 1 else 0.5)
            deadPlayer.gameData['icon'].handlePlayerDied()
            self.gameData['spawnOrder'][0].gameData['icon'].handlePlayerSpawned()
            if len(self.players) > 1:
                self.gameData['spawnOrder'][1].gameData['icon'].handlePlayerSpawned()
        else:
            team = deadPlayer.getTeam()
            if team.getID() == 0:
                x = -60
                xOffs = -78
            else:
                x = 60
                xOffs = 78
            for i,player in enumerate(team.gameData['spawnOrder']):
                player.gameData['icon'].setPositionAndScale((x + xOffs * ((0.8 if i > 0 else 0) + max(i - 1, 0) * 0.56),(40 if i == 0 else 25)), 0.5)
            deadPlayer.gameData['icon'].handlePlayerDied()
            team.gameData['spawnOrder'][0].gameData['icon'].handlePlayerSpawned()

    def _getSpawnPoint(self,player):
        # in solo-mode, if there's an existing live player on the map, spawn at whichever
        # spot is farthest from them (keeps the action spread out)
        livingPlayer = None
        if isinstance(self.getSession(),bs.FreeForAllSession):
            for player in self.players:
                if player.isAlive():
                    p = player.actor.node.position
                    livingPlayer = player
                    livingPlayerPos = p
                    break
        else:
            for team in self.teams:
                for player in team.players:
                    if player.isAlive():
                        p = player.actor.node.position
                        livingPlayer = player
                        livingPlayerPos = p
                        break
        if livingPlayer:
            playerPos = bs.Vector(*livingPlayerPos)
            points = []
            if isinstance(self.getSession(),bs.FreeForAllSession):
                for i in range(2):
                    startPos = bs.Vector(*self.getMap().getStartPosition(i))
                    points.append([(startPos-playerPos).length(),startPos])
            else:
                for team in self.teams:
                    startPos = bs.Vector(*self.getMap().getStartPosition(team.getID()))
                    points.append([(startPos-playerPos).length(),startPos])
            points.sort()
            return points[-1][1]
        else:
            return None

    def _spawnNextPlayer(self,deadPlayer):
        if isinstance(self.getSession(), bs.FreeForAllSession):
            if self._spawnTimer1 == None:
                self._tryDropPowerups()
                self._spawnTimer1 = bs.Timer(250, bs.WeakCall(self._delayedSpawnPlayer), timeType = 'game')
            elif self._spawnTimer2 == None:
                self._spawnTimer2 = bs.Timer(250, bs.WeakCall(self._delayedSpawnPlayer), timeType = 'game')
        else:
            team = deadPlayer.getTeam()
            if team.getID() == 0:
                if self._spawnTimer1 == None:
                    if self._spawnTimer2 == None:
                        self._tryDropPowerups()
                    self._spawnTimer1 = bs.Timer(250, bs.WeakCall(self._spawnPlayerFromTeam,deadPlayer.getTeam()), timeType = 'game')
            else:
                if self._spawnTimer2 == None:
                    if self._spawnTimer1 == None:
                        self._tryDropPowerups()
                    self._spawnTimer2 = bs.Timer(250, bs.WeakCall(self._spawnPlayerFromTeam,deadPlayer.getTeam()), timeType = 'game')

    def _spawnPlayerFromTeam(self,team):
        if team.getID() == 0:
            self._spawnTimer1 = None
        else:
            self._spawnTimer2 = None
        if len(team.gameData['spawnOrder']) > 0:
            self.spawnPlayer(team.gameData['spawnOrder'][0])

    def _delayedSpawnPlayer(self):
        if self._spawnTimer1 is not None:
            self._spawnTimer1 = None
            if len(self.players) > 1 and self.gameData['spawnOrder'][0].gameData['alive'] and not self.gameData['spawnOrder'][1].gameData['alive']:
                self.spawnPlayer(self.gameData['spawnOrder'][1])
            elif len(self.players) > 0 and not self.gameData['spawnOrder'][0].gameData['alive']:
                self.spawnPlayer(self.gameData['spawnOrder'][0])
        elif self._spawnTimer2 is not None:
            self._spawnTimer2 = None
            if len(self.players) > 1 and not self.gameData['spawnOrder'][1].gameData['alive']:
                self.spawnPlayer(self.gameData['spawnOrder'][1])

    def spawnPlayer(self,player):
        bs.playSound(self._swipsound)
        player.gameData['alive'] = True
        if not self.hasEnded():
            self.spawnPlayerSpaz(player,self._getSpawnPoint(player))

        # if we have any icons, update their state
        player.gameData['icon'].handlePlayerSpawned()

    def _startNextBattle(self, deadPlayer):
        if isinstance(self.getSession(), bs.FreeForAllSession):
            if len(self.players) > 0:
                self._spawnNextPlayer(deadPlayer)
                self._rearrangeIcons(deadPlayer)
        else:
            if len(deadPlayer.getTeam().players) > 0:
                self._spawnNextPlayer(deadPlayer)
                self._rearrangeIcons(deadPlayer)

    def onPlayerLeave(self,player):
        bs.TeamGameActivity.onPlayerLeave(self,player)

        if isinstance(self.getSession(), bs.FreeForAllSession):
            if self.gameData['spawnOrder'].index(player) == 0 or self.gameData['spawnOrder'].index(player) == 1:
                self.gameData['spawnOrder'].remove(player)
                if len(self.players) > 1:
                    self._spawnNextPlayer(player)
            else:
                self.gameData['spawnOrder'].remove(player)

            if len(self.players) > 0:
                self._rearrangeIcons(player)
        else:
            if player.getTeam().gameData['spawnOrder'].index(player) == 0:
                player.getTeam().gameData['spawnOrder'].remove(player)
                if len(player.getTeam().players) > 0:
                    self._spawnNextPlayer(player)
            else:
                player.getTeam().gameData['spawnOrder'].remove(player)

            if len(player.getTeam().players) > 0:
                self._rearrangeIcons(player)

        player.gameData['icon'] = None
        if player.sessionData.has_key('spawnOrderPosition'):
            player.sessionData.pop('spawnOrderPosition')

    def _clearAllTNTs(self):
        pts = self.getMap().tntPoints
        for i,pt in enumerate(pts):
            self.allTNTs[i] = None

    def _clearAllPowerups(self):
        pts = self.getMap().powerupSpawnPoints
        for i,pt in enumerate(pts):
            self.allPowerups[i] = None

    def setupStandardPowerupDrops(self):
        if not self._customPowerupRespawn:
            bs.TeamGameActivity.setupStandardPowerupDrops(self)
        else:
            pts = self.getMap().powerupSpawnPoints
            for i,pt in enumerate(pts):
                self.allPowerups.append(None)
            pts = self.getMap().tntPoints
            for i,pt in enumerate(pts):
                self.allTNTs.append(None)
            #self._tryDropPowerups()

    def _tryDropPowerups(self):
        if self._customPowerupRespawn:
            if isinstance(self.getSession(), bs.FreeForAllSession):
                if len(self.gameData['spawnOrder']) >= 2:
                    self._standardDropPowerups()
            else:
                if len(self.teams[0].gameData['spawnOrder']) > 0 and len(self.teams[1].gameData['spawnOrder']) > 0:
                    self._standardDropPowerups()

    def _standardDropTNT(self,index):
        import bsBomb
        self.allTNTs[index] = bs.Bomb(position = self.getMap().tntPoints[index], bombType = 'tnt')

    def _standardDropPowerup(self,index,expire=True):
        if not self._customPowerupRespawn:
            bs.TeamGameActivity._standardDropPowerup(self,index,expire)
        else:
            import bsPowerup
            expire = not self._keepPowerupsAliveWhenFighting
            self.allPowerups[index] = bsPowerup.Powerup(position=self.getMap().powerupSpawnPoints[index], powerupType=bs.Powerup.getFactory().getRandomPowerupType(),expire=expire)

    def _standardDropPowerups(self):
        if not self._customPowerupRespawn:
            bs.TeamGameActivity._standardDropPowerups(self)
        else:
            """
            Standard powerup drop.
            """
            # drop one powerup and tnt per point
            self._clearAllTNTs()
            pts = self.getMap().tntPoints
            for i,pt in enumerate(pts):
                bs.gameTimer(250,bs.WeakCall(self._standardDropTNT,i))
            self._clearAllPowerups()
          #  pts = self.getMap().powerupSpawnPoints
         #   for i,pt in enumerate(pts):
          #      bs.gameTimer(250,bs.WeakCall(self._standardDropPowerup,i))

    def onBegin(self):
        bs.TeamGameActivity.onBegin(self)
        self.allPowerups = []
        self.allTNTs = []
        self.setupStandardTimeLimit(self.settings['Time Limit'])
        self._customPowerupRespawn = self.settings['Respawn Powerups When Fights Finish']
        self._keepPowerupsAliveWhenFighting =  self.settings['Keep Powerups Alive When Fighting']
        self.setupStandardPowerupDrops()
        self.chunk=random.choice(["slime","ice","spark",'sweat'])

        self._vsText = bs.NodeActor(bs.newNode("text",
                                               attrs={'position':(0,105),
                                                      'hAttach':"center",
                                                      'hAlign':'center',
                                                      'maxWidth':200,
                                                      'shadow':0.5,
                                                      'vrDepth':390,
                                                      'scale':0.6,
                                                      'vAttach':"bottom",
                                                      'color':(0.8,0.8,0.3,1.0),
                                                      'text':bs.Lstr(resource='vsText')}))
        self.modpack = bs.NodeActor(bs.newNode('text',
                                               attrs={'vAttach': 'bottom',
                                                      'hAttach': 'right',
                                                      'hAlign': 'right',
                                                      'color': (0.666, 0.1, 0.1),
                                                      'flatness': 1.0,
                                                      'shadow': 1.0,
                                                      'scale': 0.85,
                                                      'position': (-150, 640),
                                                      'text': u'qq群:483552447'}))
        self.tagpack = bs.NodeActor(bs.newNode('text',
                                               attrs={'vAttach': 'bottom',
                                                      'hAttach': 'left',
                                                      'hAlign': 'left',
                                                      'color': (1, 1, 1),
                                                      'flatness': 1.0,
                                                      'shadow': 1.0,
                                                      'scale': 0.55,
                                                      'position': (160,650),
                                                      'text': u'/tag可以自定义标签,/ego获取自己信息,/top获取排行榜信息🤭'}))
        if isinstance(self.getSession(), bs.FreeForAllSession):
            self.gameData['spawnOrder'] = []

        self._addPlayersToSpawnQueue()

        self._addIcons()

        self._spawnTimer1 = None
        self._spawnTimer2 = None

        self._spawnPlayers()

        self._scoreToWin = None
        if isinstance(self.getSession(), bs.FreeForAllSession):
            self._scoreToWin = self.settings['Kills to Win Per Player']
        else:
            self._scoreToWin = self.settings['Kills to Win Per Team']
        self._showScoreBoard()
        bs.getActivity().autoTint = True
        tint = bs.getSharedObject('globals').tint
        c = bs.newNode("combine",attrs={'input0':tint[0],'input1':tint[1],'input2':tint[2],'size':3})
        bs.animate(c,'input0',{0:tint[0],10000:tint[0]*1.2,20000:tint[0]*1.4,30000:tint[0]*1.6,40000:tint[0]*1.4,50000:tint[0]*1.2,60000:tint[0],70000:0.6,80000:0.2,90000:0,100000:0,110000:0,130000:0,150000:0.2,170000:0.6,190000:tint[0]},loop=True)
        bs.animate(c,'input1',{0:tint[1],10000:tint[1]*1.2,20000:tint[1]*1.4,30000:tint[1]*1.6,40000:tint[1]*1.4,50000:tint[0]*1.2,60000:tint[1],70000:0.3,80000:0.2,90000:0,100000:0,110000:0,130000:0,150000:0.2,170000:0.3,190000:tint[1]},loop=True)
        bs.animate(c,'input2',{0:tint[2],10000:tint[2]*1.2,20000:tint[2]*1.4,30000:tint[2]*1.6,40000:tint[2]*1.4,50000:tint[0]*1.2,60000:tint[2],70000:0.3,80000:0.6,90000:1,100000:0,110000:0,130000:1,150000:0.6,170000:0.3,190000:tint[2]},loop=True)
        def superkostil():
            bs.getActivity().stdTint = bs.getSharedObject('globals').tint
            if bs.getActivity().autoTint == True:
                c.connectAttr('output',bs.getSharedObject('globals'),'tint')
                print bs.getSharedObject('globals').tint
       # self.updateTimer = bs.gameTimer(1, superkostil,repeat = True)
        #superkostil()

        #self.color_afernoon()
      #  if random.randint(1,5)==1:
      #      self.happyThoughtsMode()
        self.check_time()
        bs.gameTimer(30, bs.Call(self.dropBGD), repeat=True)
        #开局中心放炸弹
        self.set_a_bomb()

    def check_time(self):
        now = datetime.now()
        hour = now.hour
        print now
        if 4 <= hour < 8:
            self.color_morning()
        elif 8 <= hour < 16:
            self.colot_normal()
        elif 16 <= hour < 18:
            self.color_afternoon()
        else:
            self.color_night_half()
    def set_a_bomb(self):
        def get_map_center(game,_):
            pts = game.getMap().ffaSpawnPoints
            if not pts:
                return (0, 2, 0)  # 没有点时默认
            x = sum(p[0] for p in pts) / len(pts)
            y = sum(p[1] for p in pts) / len(pts)
            z = sum(p[2] for p in pts) / len(pts)
            if _:
                return (x , y + 1, z )  # 高度加5，避免卡地板
            random_height = random.uniform(-2, 2)  # 在3~6之间随机高度
            return (x+ random_height, y + 1, z+ random_height)  # 高度加5，避免卡地板

        def spawn_firework_center(game):
            center_pos = get_map_center(game, True)
            FireworkBomb(position=center_pos)
        #    for _ in range(20):
       #         center_pos = get_map_center(game,False)
       #         FireworkBomb(position=center_pos)
        bs.gameTimer(200, bs.Call(spawn_firework_center, self))



    def colot_normal(self):

        #g.ambientColor = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
      #  g.vignetteOuter = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
      #  g.vignetteInner = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
       # g.vrCameraOffset = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
        #bs.getActivity().stdTint = bs.getSharedObject('globals').tint
        pass
    def happyThoughtsMode(self):
        g = bs.getSharedObject('globals')
        g.happyThoughtsMode = True
        bs.getActivity().stdTint = g

    def color_morning(self):
        g = bs.getSharedObject('globals')
        g.tint = (1.3, 1.2, 1.0)
        g.ambientColor = (1.3, 1.2, 1.0)
        g.vignetteOuter = (0.57, 0.57, 0.57)
        g.vignetteInner = (0.9, 0.9, 0.9)
        g.vrCameraOffset = (0, -0.8, -1.1)
        g.vrNearClip = 0.5
        bs.getActivity().stdTint = g
    def color_afternoon(self):
        g = bs.getSharedObject('globals')#green noon

        g.shadowOffset = (0.0, 8.0, 5.0)
        g.tint = (1.3, 1.23, 1.0)
        g.ambientColor = (1.3, 1.23, 1.0)
        g.vignetteOuter = (0.64, 0.59, 0.69)
        g.vignetteInner = (0.95, 0.95, 0.93)
        g.vrNearClip = 1.0
        bs.getActivity().stdTint = g
    def color_night(self):
        g = bs.getSharedObject('globals')
        g.tint = (0.2, 0.2, 0.8)
        g.ambientColor = (0.2, 0.2, 0.8)
        g.vignetteOuter = (0.2, 0.2, 0.55)
        g.vignetteInner = (0.2, 0.2, 0.93)

        bs.getActivity().stdTint = g
    def color_night_half(self):
        g = bs.getSharedObject('globals')
        g.tint = (1, 1, 1.2)
        g.ambientColor = (1, 1, 1.3)
        g.vignetteOuter = (0.60, 0.62, 0.66)
        g.vignetteInner = (0.97, 0.95, 0.93)
        g.vrCameraOffset = (-1.4, 0, 0)
        bs.getActivity().stdTint =g
    def color_ending_red(self):
        g = bs.getSharedObject('globals')
        # g.tint = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
        g.ambientColor = (0.6, 0.4, 0.4)  # 浅红，整体更亮
        g.vignetteOuter = (2.6, 0.62, 0.66)
        g.vignetteInner = (2.6, 0.95, 0.93)
        # g.vrCameraOffset = (-1.4, 0, 0)
        bs.getActivity().stdTint = g


    def dropBGD(self):
        pos = (-15+(random.random()*30),
                       15,
                       -15+(random.random()*30))

        vel = ((-5.0+random.random()*30.0)*(-1.0 if pos[0] > 0 else 1.0),
                        -50.0,
                        random.uniform(-20,20))


       # print chunk
        bs.emitBGDynamics(
                    position=pos,
                    velocity=vel,
                    count=10,
                    scale=0.66+random.random(),
                    spread=0,
                    chunkType=self.chunk)

        #bs.gameTimer(20, bs.Call(self.dropBGD), repeat=True)

    def addLightColor(self):
        self.light = bs.newNode("light", attrs={"color": (1, 0, 0),
                                                "heightAttenuated": False,
                                                "radius": 999})
      #  bsUtils.animate(self.light, "color", {0: 0.1, 250: 0.3, 500: 0.1}, loop=True)
        bs.animate(self.light, "intensity", {0: 1.0, 1000: 1.8, 2000: 1.0}, loop=True)

    def handleMessage(self,m):

        if isinstance(m,bs.PlayerSpazDeathMessage):
                try:
                    bs.TeamGameActivity.handleMessage(self, m)  # augment standard behavior
                    player = m.spaz.getPlayer()

                    player.gameData['alive'] = False

                    if isinstance(self.getSession(), bs.FreeForAllSession):
                        self.gameData['spawnOrder'].remove(player)
                        self.gameData['spawnOrder'].append(player)
                    else:
                        player.getTeam().gameData['spawnOrder'].remove(player)
                        player.getTeam().gameData['spawnOrder'].append(player)

                    self._startNextBattle(player)

                    killer = m.killerPlayer
                    if killer is None: return

                    killerTeam = killer.getTeam()

                    # print player.getIcon()
                    # print killerTeam.gameData['score']
                    if killerTeam.gameData['score'] >= 1:
                        if self._scoreToWin - killerTeam.gameData['score'] == 2:
                            self.color_ending_red()
                        else:
                            self.check_time()

                    if killerTeam is player.getTeam():
                        if isinstance(self.getSession(), bs.FreeForAllSession):
                            if True:
                                if self.settings['Reduce score on suicide']:
                                    killerTeam.gameData['score'] -= 1
                                else:
                                    killerTeam.gameData['score'] = max(killerTeam.gameData['score'] - 1, 0)
                                self._scoreBoard.setTeamValue(killerTeam, killerTeam.gameData['score'], self._scoreToWin)
                        else:
                            bs.playSound(bs.Spaz.getFactory().singlePlayerDeathSound)
                            otherTeam = None
                            if killerTeam.getID() == 0:
                                otherTeam = self.teams[1]
                            else:
                                otherTeam = self.teams[0]
                            killerTeam = otherTeam
                            killerTeam.gameData['score'] += 1
                            self._scoreBoard.setTeamValue(killerTeam, killerTeam.gameData['score'], self._scoreToWin)
                            if killerTeam.gameData['score'] == self._scoreToWin:
                                self.endGame()
                    else:
                        bs.playSound(bs.Spaz.getFactory().singlePlayerDeathSound)
                        killerTeam.gameData['score'] += 1
                        self._scoreBoard.setTeamValue(killerTeam, killerTeam.gameData['score'], self._scoreToWin)
                        if killerTeam.gameData['score'] == self._scoreToWin:
                            self.endGame()
                except:
                    try:
                        for i in bs.getSession().players:
                            try:
                                i.actor.node.handleMessage(bs.DieMessage())
                            except:
                                pass
                    except:
                        pass
                    try:
                        bsInternal._getForegroundHostActivity().endGame()
                    except:
                        pass

    def _getLivingTeams(self):
        return [team for team in self.teams if len(team.players) > 0 and any(player.gameData['lives'] > 0 for player in team.players)]

    def _showScoreBoard(self):
        for team in self.teams:
            self._scoreBoard.setTeamValue(team,0,self._scoreToWin)

    def endGame(self):
        if self.hasEnded(): return
        results = bs.TeamGameResults()

        for team in self.teams:
            results.setTeamScore(team, team.gameData['score'])
        blessings = [
            "lol",
        ]
     #   bsInternal._chatMessage(random.choice(blessings))
        bsInternal._chatMessage(str(time.time()))

        def addLightColor():

            g = bs.getSharedObject('globals')
            # g.tint = (1.2000000476837158, 1.100000023841858, 0.9700000286102295)
            g.ambientColor = (0.3, 0, 0)  # Darker ambient red
            g.vignetteOuter = (2.6, 0.62, 0.66)
            g.vignetteInner = (2.6, 0.95, 0.93)
            # g.vrCameraOffset = (-1.4, 0, 0)
            bs.getActivity().stdTint = g
        bs.gameTimer(10, addLightColor)
        def e():
            self.end(results=results)
        celebrate(600)
        bs.gameTimer(600, e)


    def onFinalize(self):
        bs.TeamGameActivity.onFinalize(self)
        with bs.Context(self):
            self._vsText = None # kill our 'vs' if its there
            if self.settings['Preserve queue through games']:
                self._savePlayerPositionsForLaterUse()

    def _savePlayerPositionsForLaterUse(self):
        if isinstance(self.getSession(), bs.FreeForAllSession):
            for i,player in enumerate(self.gameData['spawnOrder']):
                player.sessionData['spawnOrderPosition'] = i
        else:
            for team in self.teams:
                for i,player in enumerate(team.gameData['spawnOrder']):
                    player.sessionData['spawnOrderPosition'] = i


class FireworkBomb(bsBomb.Bomb):
    def __init__(self, position=(0,1,0), velocity=(0,0,0), explodeDelay=1500):
        bsBomb.Bomb.__init__(self,
                             bombType='normal',
                             position=position,
                             velocity=velocity
                            )
        bs.gameTimer(explodeDelay, bs.WeakCall(self._forceExplode))
    def _forceExplode(self):
        if self.node.exists():
            self.handleMessage(bsBomb.ExplodeMessage())
    def handleMessage(self, msg):
        if isinstance(msg, bsBomb.ExplodeMessage):
            pos = None
            if self.node.exists():
                pos = self.node.position
            self._doFireworkBlast(pos)
            self.handleMessage(bs.DieMessage())
        else:
            bsBomb.Bomb.handleMessage(self, msg)

    def _doFireworkBlast(self, pos):
        if pos is None:
            return

        bs.emitBGDynamics(position=pos, velocity=(0, 7, 0), count=random.randint(500, 1000),
                              scale=0.3 + random.random() * 1.1,
                              spread=0.2, chunkType='spark')
        celebrate(1000)
        bs.playSound(bs.getSound('cheer'))

def celebrate(int):
    for player in bs.getSession().players:
        if player.isAlive():
            spaz = player.actor
            if spaz is not None and spaz.isAlive():
                player.actor.node.handleMessage('celebrate', int)

