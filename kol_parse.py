#!/usr/bin/env python
from __future__ import print_function, division, unicode_literals
'''
Parse a KoLMafia log of one or more encounters and produce a report of
things like stat gains, meat drop, and item drop rates.

For best results, turn on "Session log records your player's state on login"
in preferences, and restart whenever your modifiers change.

Things to watch out for:
*	How to properly detect the end of a fight?
	*	Possible (maybe partial) fix: when getting meat or items, check that we
		haven't already gotten stats.
*	Your familiar's actions can screw up the script if its name is something
	like, "You acquire an item:".  Why would you do such a thing?
*	Monsters with randomized names, e.g. hobos and elfs, are not
	identified properly if they don't take any damage.

Tested in Python 3.3
'''

import sys
import os
import time
import re
import io

try:
    import html.parser as html_parser
except ImportError:
    import HTMLParser as html_parser

#Classes

class toolbox(object):
	errors = []
	logpath = "kol_parse.txt"
	logfile = None
	html_parser = html_parser.HTMLParser()
	statnums = {
			0 : "Muscle",
			1 : "Mysticality",
			2 : "Moxie" }
	statwords = {}
	for word in (
			"Muscle", "Mus", "0",
			"Beefiness", "Fortitude", "Muscleboundness", "Strengthliness", "Strongness",
			"Seal Clubber", "Turtle Tamer", "Avatar of Boris", "Zombie Master" ):
		statwords[word] = 0
		statwords[word.title()] = 0
		statwords[word.lower()] = 0
	for word in (
			"Mysticality", "Mys", "1",
			"Enchantedness", "Magicalness", "Mysteriousness", "Wizardliness",
			"Pastamancer", "Sauceror", "Mysticism" ):
		statwords[word] = 1
		statwords[word.title()] = 1
		statwords[word.lower()] = 1
	for word in (
			"Moxie", "Mox", "2",
			"Cheek", "Chutzpah", "Roguishness", "Sarcasm", "Smarm",
			"Disco Bandit", "Accordion Thief" ):
		statwords[word] = 2
		statwords[word.title()] = 2
		statwords[word.lower()] = 2
	html_head = '''<html><head><meta charset="UTF-8">
	<style type="text/css">
		body {font-family: sans-serif; font-size: small;}
		h4 {margin-bottom: 0;}
		.invis {display: none;}
		div#anal, div#details, div#item {background-color: #eeeeee;}
	</style>
	<script src="http://ajax.googleapis.com/ajax/libs/jquery/1.4.2/jquery.min.js"></script>
	<script type="text/javascript">
		function toggle_invis(target, button)
		{
			if( button )
			{
				if( button.value=="Expand" )
				{
					$(target).find("div.invis").attr("class", "uninvis");
					button.value="Collapse";
				}
				else
				{
					$(target).find("div.uninvis").attr("class", "invis");
					button.value="Expand";
				}
			}
			else
			{
				if( target.className == "invis" )
					target.className = "uninvis";
				else
					target.className = "invis";
			}
		}
	</script>\n</head>\n<body>\n'''
	html_foot = "</body></html>"

class searches(object):
	a = "\\A"
	z = "\\Z"
	re_charclass  = re.compile( a+"Class: ([ A-DMPSTZa-fhil-or-v]+)"+z )
	re_statbase   = re.compile( a+"(Mus|Mys|Mox): (\\d+)( \\((\\d+)\\))?, tnp = \\d+" )
	re_statday    = re.compile( a+"([A-Za-z]+) bonus today" )
	re_bonus_crap = re.compile( a+"(ML|Enc|Init|Exp|Meat|Item): ([\\+\\-][\\d]+\\.?\\d*)%?"+z )
	re_bbs_tag    = re.compile(   "\\[kol_parse\\];" )
	re_bbs_info   = re.compile(   " ([^=;]+)=([^=;]+);" )
	re_adventure  = re.compile( a+"\\[(\\d+)\\] (.+)" )
	re_encounter  = re.compile( a+"Encounter: (.+)" )
	re_round      = re.compile( a+"Round (\\d+):" )
	re_jump       = re.compile(   " wins initiative!" )
	re_steal      = re.compile(   " tries to steal an item!" )
	re_ravesteal  = re.compile( a+"Rave combo: Rave Steal"+z )
	re_deal       = re.compile(   " brokers a quick deal, and splits the profits with you." )
	re_mondmg     = re.compile(   ": (.+) takes (\\d+) damage\\."+z )
	re_losehp     = re.compile( a+"You lose (\\d+) hit points?"+z )
	re_geteffect  = re.compile( a+"You acquire an effect: (.+) \\(duration: (\\d+)" )
	re_win        = re.compile(   " wins the fight!" )
	re_meat       = re.compile( a+"You gain (\\d+) Meat" )
	re_item       = re.compile( a+"You acquire an item: (.+)" )
	re_multi_item = re.compile( a+"You acquire (.+) \\((\\d+)\\)"+z )
	re_gainstat   = re.compile( a+"You gain (\\d+) ([BCEFMRSWa-ik-pr-uyz]+)"+z )
	re_statpoint  = re.compile( a+"You gain a (Muscle|Mysticality|Moxie) point!" )
	def __init__(self, line=""):
		self.meta = False
		self.outside_combat = False
		self.search(line)
	def search(self, line):
		# I'm not sure why this next statement is here, line is already a
		# unicode object in 2.x and a str in 3.x.
		#line = str(line)
		self.charclass = searches.re_charclass.search( line )
		self.statbase = searches.re_statbase.search( line )
		self.statday = searches.re_statday.search( line )
		self.bonus_crap = searches.re_bonus_crap.search( line )
		self.bbs_tag = searches.re_bbs_tag.search( line )
		self.bbs_info = []
		start = 0;
		while self.bbs_tag:
			match = searches.re_bbs_info.search( line, start )
			if match:
				self.bbs_info.append( match )
				start = match.end()
			else:
				break
		self.adventure = searches.re_adventure.search( line )
		self.encounter = searches.re_encounter.search( line )
		self.round = searches.re_round.search( line )
		self.jump = searches.re_jump.search( line )
		self.steal = searches.re_steal.search( line )
		self.ravesteal = searches.re_ravesteal.search( line )
		self.deal = searches.re_deal.search( line )
		self.mondmg = searches.re_mondmg.search( line )
		self.losehp = searches.re_losehp.search( line )
		self.geteffect = searches.re_geteffect.search( line )
		self.win = searches.re_win.search( line )
		self.meat = searches.re_meat.search( line )
		self.item = searches.re_item.search( line )
		self.multi_item = searches.re_multi_item.search( line )
		self.gainstat = searches.re_gainstat.search( line )
		self.statpoint = searches.re_statpoint.search( line )
		if(		self.charclass or
				self.statbase or
				self.statday or
				self.bonus_crap or
				self.bbs_info ):
			self.outside_combat = True
		if(		self.charclass or
				self.statbase or
				self.statday or
				self.bonus_crap or
				self.bbs_info or
				self.statpoint ):
			self.meta = True

class encounter(object):
	def __init__(self):
		self.num = 0
		self.location = ""
		self.title = ""
		self.monstername = None
		self.metadata = metadata_class()
		self.iscombat = False
		self.jump = False
		self.effects = []
		self.won = False
		self.mondamages = {}
		self.meat = 0
		self.items = []
		self.stolenitems = []
		self.miscitems = []
		self.stats = [0, 0, 0]
	def copy(self):
		enc = encounter()
		enc.num = self.num
		enc.location = self.location
		enc.title = self.title
		enc.monstername = self.monstername
		enc.metadata = self.metadata
		enc.iscombat = self.iscombat
		enc.jump = self.jump
		enc.won = self.won
		for key in self.mondamages:
			enc.mondamages[key] = self.mondamages[key].copy()
		enc.meat = self.meat
		enc.items = self.items.copy()
		enc.stolenitems = self.stolenitems.copy()
		enc.miscitems = self.miscitems.copy()
		enc.stats = self.stats.copy()
		return enc
	def __str__(self):
		st = "Combat" if self.iscombat else "Noncombat"
		st += " #%d" % self.num
		if self.location:
			st += " (%s)" % self.location
		if self.monstername:
			st += ": %s" % self.monstername
		elif self.title:
			st += ": %s" % self.title
		return st
	def __gt__(self, other):
		return self.title > other.title
	def __lt__(self, other):
		return self.title < other.title
	def overview(self):
		st = str(self)
		if self.items:
			st += "\nFound %s" % self.items
		if self.stolenitems:
			st += "\Stole %s" % self.stolenitems
		if self.miscitems:
			st += "\nSomehow gained %s" % self.miscitems
		if sum( [sum(self.mondamages[key]) for key in self.mondamages] ):
			st += "\nMonster took damage %s" % self.mondamages
		if sum(self.stats):
			st += "\nGained stats %s" % self.stats
		return st

class monster(object):
	def __init__(self, name):
		self.name = str(name)
		self.encountered = 0
		self.encounters = []
		self.gotjump = []
		self.gotjumped = []
		self.jump_inits = []
		self.jumped_inits = []
		self.initguess = [None, None, None]
		self.defeated = 0
		self.hps = []
		self.meats = []
		self.meat = 0.0
		self.itemdict = {}
		self.items = []
		self.stats = []
		self.stat = 0.0
		self.level = 0
	def __str__(self):
		return "Monster: " + self.name
	def __gt__(self, other):
		return self.name > other.name
	def __lt__(self, other):
		return self.name < other.name
	def addstats(self, enc, metadata):
		multipliers = [1.0, 1.0, 1.0]
		if metadata.mainstatnum in toolbox.statnums:
			# Assume a moon sign that gives +10% to your mainstat
			multipliers[metadata.mainstatnum] += 0.1
		else:
			log_error( "*** Invalid class: %s" % str(metadata.charclass) )
			log_error( "*** (Is \"Session log records your player's state on login\" turned on?)" )
		if metadata.statdaynum in toolbox.statnums and enc.num > 1000:
			multipliers[metadata.statdaynum] += 0.25
		self.stats.append(
			enc.stats[0] / multipliers[0] +
			enc.stats[1] / multipliers[1] +
			enc.stats[2] / multipliers[2] -
			metadata.stat )
	def crunch(self):
		if self.stats:
			self.stats.sort()
			self.stat = sum(self.stats) / len(self.stats)
			self.level = int( self.stat * 4 )
		if self.meats:
			self.meats.sort()
			self.meat = sum(self.meats) / len(self.meats)
		self.jump_inits = []
		self.jumped_inits = []
		if self.gotjump:
			self.jump_inits = [
				initiative + max( mainstat - self.level - ml, 0 )
				for initiative, mainstat, ml in self.gotjump ]
			self.initguess[2] = min(self.jump_inits) + 99
		else:
			self.initguess[2] = None
		if self.gotjumped:
			self.jumped_inits = [
				initiative + max( mainstat - self.level - ml, 0 )
				for initiative, mainstat, ml in self.gotjumped ]
			self.initguess[1] = max(self.jumped_inits) + 1
		else:
			self.initguess[1] = None
		meaningful_jumps = []
		meaningful_jumpeds = []
		if self.jump_inits and self.jumped_inits:
			meaningful_jump_init = max(self.jumped_inits)
			meaningful_jumped_init = min(self.jump_inits)
			meaningful_jumps = [i for i in self.jump_inits if i <= meaningful_jump_init]
			meaningful_jumpeds = [i+100 for i in self.jumped_inits if i <= meaningful_jumped_init]
		if meaningful_jumps and self.jumped_inits:
			total = float( sum(meaningful_jumps) + sum(meaningful_jumpeds) )
			n = len(meaningful_jumps) + len(meaningful_jumpeds)
			self.initguess[0] = int( total / n + 0.5 )
		else:
			self.initguess[0] = None
	def details(self):
		self.crunch()
		st = ""
		if self.stats:
			st += "\n Stats (avg %.1f):" % self.stat
			st += '\n' + ';'.join( ["%.2f" % stat for stat in self.stats] )
		if self.meats:
			st += "\n Meat (avg %.1f):" % self.meat
			st += '\n' + ';'.join( ["%.2f" % meat for meat in self.meats] )
		if self.jump_inits:
			st += "\n Got jump:"
			st += '\n' + ';'.join( ["%d" % i for i in self.jump_inits] )
		if self.jumped_inits:
			st += "\n Got jumped:"
			st += '\n' + ';'.join( ["%d" % i for i in self.jumped_inits] )
		st = "<div>" + st.strip() + "</div>"
		st = "<h4 onclick='toggle_invis(this.nextSibling)'>%s (%d encountered, %d defeated)</h4>" % (
			self.name, self.encountered, self.defeated ) + st
		return st
	def itemdetails(self):
		st = ""
		for thing in self.items:
			dropped = []
			notdropped = []
			stolen = 0
			unknown = 0
			for enc in self.encounters:
				if thing.name in enc.stolenitems:
					stolen += 1
					continue
				if not enc.metadata or enc.metadata.item is None:
					unknown += 1
					continue
				if thing.name in enc.items:
					dropped.append( enc.metadata.item )
				else:
					notdropped.append( enc.metadata.item )
			dropped.sort()
			notdropped.sort(reverse=True)
			if dropped:
				st += "\n(%s) %d drops: " % ( thing.name, len(dropped) )
				st += " ".join( ["%.2f" % rate for rate in dropped] )
			if notdropped:
				st += "\n(%s) %d non-drops: " % ( thing.name, len(notdropped) )
				st += " ".join( ["%.2f" % rate for rate in notdropped] )
			if stolen:
				st += "\n(%s) %d stolen" % ( thing.name, stolen )
			if unknown:
				st += "\n(%s) %d encounter(s) missing item drop rate data" % ( thing.name, unknown )
		st = "<div>" + st.strip() + "</div>"
		st = "<h4 onclick='toggle_invis(this.nextSibling)'>%s (%d encountered, %d defeated)</h4>" % (
			self.name, self.encountered, self.defeated ) + st
		return st
	def overview(self):
		self.crunch()
		st = "level: %d" % self.level
		if self.stats:
			st += "\n stats: %.1f [%.1f .. %.1f]" % (
				self.stat, min(self.stats), max(self.stats) )
		if self.initguess[0] is not None:
			st += "\n init: %d [%d .. %d]" % tuple(self.initguess)
		elif self.initguess[1] is not None and self.initguess[2] is not None:
			st += "\n init: ? [%d .. %d]" % ( self.initguess[1], self.initguess[2] )
		elif self.initguess[1] is not None:
			st += "\n init: ? [%d .. ?]" % self.initguess[1]
		elif self.initguess[2] is not None:
			st += "\n init: ? [? .. %d]" % self.initguess[2]
		if sum(self.meats):
			st += "\n meat: %.1f [%.1f .. %.1f]" % (
				self.meat, min(self.meats), max(self.meats) )
		else:
			st += "\n meat: None"
		for thing in self.items:
			st += "\n" + thing.overview()
		st = "<div class='uninvis'>" + st.strip() + "</div>"
		st = "<h4 onclick='toggle_invis(this.nextSibling)'>%s (%d encountered, %d defeated)</h4>" % (
			self.name, self.encountered, self.defeated ) + st
		return st

class item(object):
	def __init__(self, name=""):
		self.name = name
		self.found = 0
		self.stolen = 0 # todo: count rave-stolen items
		self.misc = 0
		self.prevented = 0 # item stolen and combat won
		self.rate = 0.0
	def __str__(self):
		return self.name
	def __gt__(self, other):
		return self.name > other.name
	def __lt__(self, other):
		return self.name < other.name
	def overview(self):
		if self.rate == 1:
			st = "100%% %s" % self.name
		elif self.rate is None:
			st = " 0%% %s" % self.name
		else:
			st = "%.1f%% %s" % (self.rate*100, self.name)
		st += " (%d drop%s" % (self.found, "s" if self.found != 1 else "")
		if self.stolen:
			st += ", %d stolen" % self.stolen
		if self.misc:
			st += ", %d other" % self.misc
		st += ")"
		return st

class metadata_class(object):
	def __init__(self):
		self.charclass = None
		self.mainstatnum = None
		self.statbases = [0, 0, 0]
		self.statpoints = [0, 0, 0]
		self.statday = None
		self.statdaynum = None
		self.ml = None
		self.combat = None
		self.init = None
		self.real_init = None
		self.stat = None
		self.meat = None
		self.item = None
	def setclass(self, charclass):
		self.charclass = charclass
		self.mainstatnum = statnum(charclass)
	def setstatbase(self, whichstat, amount):
		whichstat = statnum(whichstat)
		self.statbases[whichstat] = int(amount)
		self.statpoints[whichstat] = 0
	def gainstatpoint(self, whichstat):
		whichstat = statnum(whichstat)
		if self.statbases[whichstat]:
			self.statbases[whichstat] += 1
		else:
			self.statpoints[whichstat] += 1
	def setstatday(self, statday):
		self.statday = statday
		self.statdaynum = statnum(statday)
	def setval(self, key, val):
		key = str(key).lower()
		if key == "class":
			self.setclass(val)
		elif key == "ml":
			self.ml = int(float(val))
		elif key == "enc":
			self.combat = int(float(val))
		elif key == "init":
			self.init = int(float(val))
		elif key == "real_init":
			self.real_init = int(float(val))
		elif key == "exp":
			self.stat = float(val) * 2
		elif key == "meat":
			self.meat = float(val) / 100 + 1
		elif key == "item":
			self.item = float(val) / 100 + 1
		elif key in toolbox.statwords:
			self.setstatbase(key, val)
	def initiative(self):
		initiative = None
		mainstat = 0
		if self.mainstatnum in toolbox.statnums:
			mainstat = self.statbases[self.mainstatnum]
		if   self.ml <=  20:
			initiative = self.init
		elif self.ml <=  40:
			initiative = self.init - self.ml     +  20
		elif self.ml <=  60:
			initiative = self.init - self.ml * 2 +  60
		elif self.ml <=  80:
			initiative = self.init - self.ml * 3 + 120
		elif self.ml <= 100:
			initiative = self.init - self.ml * 4 + 200
		else:
			initiative = self.init - self.ml * 5 + 300
		return (initiative, mainstat, self.ml)
	def import_from(self, other):
		if other.charclass:
			self.setclass(other.charclass)
		for whichstat in toolbox.statnums:
			if other.statbases[whichstat]:
				self.statbases[whichstat] = other.statbases[whichstat]
			else:
				self.statbases[whichstat] += self.statpoints[whichstat]
			self.statpoints[whichstat] = other.statpoints[whichstat]
		if other.statday:
			self.setstatday(other.statday)
		if other.ml is not None:
			self.ml = other.ml
		if other.combat is not None:
			self.combat = other.combat
		if other.init is not None:
			self.init = other.init
		if other.stat is not None:
			self.stat = other.stat
		if other.meat is not None:
			self.meat = other.meat
		if other.item is not None:
			self.item = other.item
	def overview(self):
		st = "Metadata"
		if self.charclass:
			st += "\n	Class: %s" % self.charclass
			st += " (%s)" % statword( self.mainstatnum )
		if self.statday:
			st += "\n	Stat day: %s" % self.statday
		if sum(self.statbases):
			st += "\n	Stats: " + " / ".join( [str(n) for n in self.statbases] )
		for whichstat in toolbox.statnums:
			if self.statpoints[whichstat]:
				st += "\n	Gained %d " % self.statpoints[whichstat]
				st += statword( whichstat )
		if self.ml is not None:
			st += "\n	Monster level adjustment: %+d" % self.ml
		if self.combat is not None:
			st += "\n	Combat rate modifier: %+d%%" % self.combat
		if self.init is not None:
			st += "\n	Initiative bonus: %+d%%" % self.init
			if self.ml is not None and self.ml > 20:
				st += " (%d after ML)" % self.initiative()[0]
		if self.stat is not None:
			st += "\n	Bonus stats: %+.2f" % self.stat
		if self.meat is not None:
			st += "\n	Meat multiplier: %.4f" % self.meat
		if self.item is not None:
			st += "\n	Item multiplier: %.4f" % self.item
		return st
	def details(self):
		return self.overview()

#Functions

def log( *args, **kwargs ):
    # The signature for this method was log(*args,tag="br"), but Python 2.7 does
    # not support named arguments after a *args, so I read tag from kwargs.
	tag = kwargs.get('tag','br')
	if tag and tag != "br":
		toolbox.logfile.write( "<%s>" % tag )
	if args:
		message = " ".join( [str(arg) for arg in args] ).replace( "\n", "<br>\n" )
		toolbox.logfile.write( message )
		if tag == "br":
			toolbox.logfile.write( "<br>\n" )
		elif tag:
			if " " in tag:
				tag = tag[ : tag.find(" ") ]
			toolbox.logfile.write( "</%s>\n" % tag )
	toolbox.logfile.flush()

def logprint( *args ):
	message = ' '.join( [str(arg) for arg in args] )
	print( *args )
	log( *args )

def log_error( *args ):
	message = ' '.join( [str(arg) for arg in args] )
	toolbox.errors.append( message )
	print( *args )
	log( *args )

unescape = lambda s: toolbox.html_parser.unescape(s)

def statnum(statword):
	if statword in toolbox.statnums:
		return statword
	else:
		return toolbox.statwords[ str(statword).title() ]

def statword(whichstat):
	return toolbox.statnums[ statnum(whichstat) ]

def add_data(dic, key, val):
	'''Add val to the list at dic[key], creating it first if needed.'''
	if key in dic:
		dic[key].append(val)
	else:
		dic[key] = [val]

def parse_encounter(lines):
	'''Parse an iterable of strings.  Return (encounter object, number of lines parsed).'''
	enc = encounter()
	lines_parsed = 0
	matches = None
	round = None
	ravestealing = 0
	for line in lines:
		lines_parsed += 1
		if enc.location and not line:
			# There are no blank lines in an encounter, so this one is over.
			break
		stealing = bool( matches and matches.steal )
		dealing = bool( matches and matches.deal )
		if ravestealing:
			ravestealing -= 1
		matches = searches(line)
		if matches.adventure:
			if enc.location:
				# Looks like we bumped into the next adventure. Pack it up.
				print( "Parsing interrupted by another adventure." )
				lines_parsed -= 1
				break
			n, enc.location = matches.adventure.groups()
			enc.num = int(n)
			print( "Parsing Adventure %d:" % enc.num, enc.location )
			continue
		#
		# metadata
		#
		if matches.outside_combat and enc.location:
			lines_parsed -= 1
			break
		if matches.charclass:
			enc.metadata.setclass( matches.charclass.groups()[0] )
			continue
		if matches.statbase:
			whichstat, buffed, dummy, base = matches.statbase.groups()
			if not base:
				base = buffed
			enc.metadata.setstatbase( whichstat, base )
			continue
		if matches.statday:
			enc.metadata.setstatday( matches.statday.groups()[0] )
			continue
		if matches.bonus_crap:
			key, val = matches.bonus_crap.groups()
			enc.metadata.setval( key, val )
			continue
		if matches.statpoint:
			enc.metadata.gainstatpoint( matches.statpoint.groups()[0] )
			continue
		if matches.bbs_info:
			for m in matches.bbs_info:
				key, val = m.groups()
				enc.metadata.setval( key, val )
			continue
		#
		# encounter stuff
		#
		if not enc.location:
			# Don't record encounter data until the encounter actually begins.
			continue
		if matches.encounter:
			title, = matches.encounter.groups()
			enc.title = unescape(title)
			continue
		if matches.round:
			n, = matches.round.groups()
			round = int(n)
			enc.iscombat = True
		if matches.jump:
			enc.jump = True
			continue
		if matches.mondmg:
			name, n = matches.mondmg.groups()
			enc.monstername = unescape(name)
			add_data( enc.mondamages, round, int(n) )
			continue
		if matches.losehp:
			# todo: count damage taken
			continue
		if matches.geteffect:
			name, n = matches.geteffect.groups()
			enc.effects.append( name )
			continue
		if matches.win:
			enc.won = True
			continue
		if matches.meat:
			if sum(enc.stats):
				# You don't get meat after stats
				lines_parsed -= 1
				break
			if enc.won:
				n, = matches.meat.groups()
				enc.meat = int(n)
			continue
		if matches.ravesteal:
			ravestealing = 3
			continue
		if matches.item or matches.multi_item:
			if sum(enc.stats):
				# You don't get items after stats
				lines_parsed -= 1
				break
			itemname = ""
			num = 1
			if matches.item:
				itemname, = matches.item.groups()
			elif matches.multi_item:
				itemname, num = matches.multi_item.groups()
				num = int(num)
			if stealing or ravestealing:
				enc.stolenitems.extend( [itemname] * num )
			elif dealing:
				enc.miscitems.extend( [itemname] * num )
			elif enc.won:
				enc.items.extend( [itemname] * num )
			else:
				enc.miscitems.extend( [itemname] * num )
			continue
		if matches.gainstat and enc.won:
			n, whichstat = matches.gainstat.groups()
			n, whichstat = int(n), statnum(whichstat)
			if whichstat in toolbox.statnums:
				enc.stats[whichstat] = n
			continue
	#
	# end parsing loop
	#
	if enc.iscombat and not enc.monstername:
		enc.monstername = enc.title
	return (enc, lines_parsed)

def parselines(lines):
	'''Parse a list/tuple of lines as KoL encounters.  Return a list of encounter objects.'''
	encounters = []
	total_parsed = 0
	while total_parsed < len(lines):
		enc, lines_parsed = parse_encounter(lines[total_parsed:])
		if not (enc.location or enc.metadata):
			break
		total_parsed += lines_parsed
		encounters.append(enc)
		enc2 = alt_encounter(enc)
		if enc2:
			enc.metadata = None
			encounters.append(enc2)
	return encounters

def alt_encounter(enc):
	item_alts = {
		"morningwood plank" : "(smut orc plank)",
		"raging hardwood plank" : "(smut orc plank)",
		"weirdwood plank" : "(smut orc plank)",
		"long hard screw" : "(smut orc fastener)",
		"messy butt joint" : "(smut orc fastener)",
		"thick caulk" : "(smut orc fastener)",
		"backwoods screwdriver" : "(smut orc consumable)",
		"orcish hand lotion" : "(smut orc consumable)",
		"orcish nailing lube" : "(smut orc consumable)",
		"orcish rubber" : "(smut orc consumable)",
		"freshwater pearl necklace" : "(smut orc equipment)",
		"orc wrist" : "(smut orc equipment)",
		"orcish stud-finder" : "(smut orc equipment)",
		"screwing pooch" : "(smut orc equipment)",
	}
	monster_alts = {
		"smut orc jacker" : "(normal smut orc)",
		"smut orc nailer" : "(normal smut orc)",
		"smut orc pipelayer": "(normal smut orc)",
		"smut orc screwer" : "(normal smut orc)",
	}
	for itemlist in (enc.items, enc.stolenitems, enc.miscitems):
		for n in range(len(itemlist)):
			if itemlist[n] in item_alts:
				itemlist.append( item_alts[itemlist[n]] )
	if enc.monstername in monster_alts:
		enc2 = enc.copy()
		enc2.title = monster_alts[enc.monstername]
		return enc2

def analyze_monsters(encounters):
	monstersdict = {}
	metadata = metadata_class()
	metadata.ml = 0
	metadata.combat = 0
	metadata.init = 0
	metadata.stat = 0.0
	metadata.meat = 1.0
	metadata.item = 1.0
	for enc in encounters:
		if enc.metadata:
			metadata.import_from( enc.metadata )
		if enc.iscombat:
			log( "Analyzing", enc )
		else:
			if enc.location:
				log( "Skipping", enc )
			continue
		if enc.monstername not in monstersdict:
			monstersdict[enc.monstername] = monster( enc.monstername )
			monstersdict[enc.monstername].itemdict = {}
		mon = monstersdict[enc.monstername]
		mon.encounters.append(enc)
		mon.encountered += 1
		if enc.jump:
			mon.gotjump.append( metadata.initiative() )
		else:
			mon.gotjumped.append( metadata.initiative() )
		# todo: damage stuff
		if enc.won:
			mon.defeated += 1
			mon.addstats( enc, metadata )
			mon.meats.append( enc.meat / metadata.meat )
		inverse_itemrate = 1 / (
				metadata.item +
				( 0.2 if "Disco Concentration" in enc.effects else 0 ) +
				( 0.3 if "Rave Concentration" in enc.effects else 0 )
		)
		for itemname in enc.items:
			if itemname not in mon.itemdict:
				mon.itemdict[itemname] = item(itemname)
			mon.itemdict[itemname].found += 1
			mon.itemdict[itemname].rate += inverse_itemrate
		for itemname in enc.stolenitems:
			if itemname not in mon.itemdict:
				mon.itemdict[itemname] = item(itemname)
			mon.itemdict[itemname].stolen += 1
			if enc.won:
				mon.itemdict[itemname].prevented += 1
		for itemname in enc.miscitems:
			if itemname not in mon.itemdict:
				mon.itemdict[itemname] = item(itemname)
			mon.itemdict[itemname].misc += 1
	monsters = list( monstersdict.values() )
	monsters.sort()
	for mon in monsters:
		mon.items = list( mon.itemdict.values() )
		mon.items.sort()
		for thing in mon.items:
			d = mon.defeated - thing.prevented
			if d > 0:
				if thing.found == d:
					thing.rate = 1.0
				else:
					thing.rate = thing.rate / d
			else:
				thing.rate = None
	return monsters

#Main

def main():
	paths = sys.argv[1:]
	if not paths:
		while True:
			path = input( "File to parse: " ).strip()
			if path:
				paths.append( path )
			else:
				break
	if not paths or not paths[0]:
		return
	fn_dot = paths[0].rfind('.')
	fn_start = 1 + paths[0].rfind(os.sep)
	fn_end = fn_dot if fn_dot > fn_start else len( paths[0] )
	fn = paths[0][fn_start:fn_end]
	toolbox.logpath = paths[0][:fn_start] + "kol_parse_" + fn + ".html"
	toolbox.logfile = io.open( toolbox.logpath, "w", encoding="utf-8" )
	toolbox.logfile.write( toolbox.html_head )
	log( "kol_parse.py |", time.ctime(), tag="h3" )
	encounters = []
	for path in paths:
		print( "\n*** Parsing file: %s\n" % path )
		f = io.open(path, encoding="utf-8")
		encounters.extend( parselines( f.read().split('\n') ) )
		f.close()
	numcombats = len( [True for enc in encounters if enc.iscombat] )
	#
	log( tag="div id='anal'" )
	log( "Analyzed %d combats" % numcombats, tag="h3" )
	log( tag="input type='button' value='Expand' onclick='toggle_invis(\"div#anal\",this)'" )
	log( tag="div class='invis'" )
	monsters = analyze_monsters(encounters)
	log( tag="/div" )
	log( tag="/div" )
	#
	log( tag="div id='details'" )
	log( "Details", tag="h3" )
	log( tag="input type='button' value='Expand' onclick='toggle_invis(\"div#details\",this)'" )
	log( tag="div class='invis'" )
	for mon in monsters:
		log( mon.details(), tag="div" )
	log( tag="/div" )
	log( tag="/div" )
	#
	log( tag="div id='item'" )
	log( "Items", tag="h3" )
	log( tag="input type='button' value='Expand' onclick='toggle_invis(\"div#item\",this)'" )
	log( tag="div class='invis'" )
	for mon in monsters:
		log( mon.itemdetails(), tag="div" )
	log( tag="/div" )
	log( tag="/div" )
	#
	log( tag="div id='overview'" )
	log( "Overview", tag="h3" )
	log( tag="input type='button' value='Collapse' onclick='toggle_invis(\"div#overview\",this)'" )
	for mon in monsters:
		log( mon.overview(), tag="div" )
	log( tag="/div" )
	log( '''
Monster levels are estimated with +stat boni and stat days factored in.
+exp bonus is assumed to consist entirely of general +stats and +ML.
Moon sign is assumed to give +10% to your mainstat.
Other than moon sign and stat days, percentile bonuses to stat gains (like April Shower effects) are not considered.''' )
	if toolbox.errors:
		logprint( "\nErrors:" )
		for error in toolbox.errors:
			logprint( error )
	toolbox.logfile.close()
	try:
		os.startfile( toolbox.logpath )
	except AttributeError:
		# os.startfile only exists on Windows
		pass

main()
