kol_parse
=========

A tool for parsing kolmafia logs. This is useful for spading the game Kingdom
of Loathing.

REQUIREMENTS
------------
* python 2.7 or 3.3

USAGE
-----

    ./kol_parse.py [log files]

If you set `bbs_kol_parse.ash` as your pre-adventure script in KolMafia
preferences, it will log additional statistics.  You do not need
`bbs_kol_parse.ash` to use `kol_parse`, but if you do use it `kol_parse` will
be able to calculate more stats such as item drop rates.

This is very much alpha software. Make sure you understand what is happening
when you spade. Please don't just run this for a few adventures and then go
edit the kol wiki.

HISTORY
-------

kol_parse was originally created by DentArthurDent. JeffAMcGee backported it
from python 3.3 to 2.7.
