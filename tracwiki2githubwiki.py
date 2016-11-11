#!/usr/bin/python
#
# Utility for transforming and transferring a Trac wiki to github
#
# Copyright (c) 2016 Red Hat Inc.
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

"""
trac2github - a tool for transforming a Trac wiki, as contained in an exported sqlite3
database, into a github-wiki git repository
"""

import csv
import logging
import os
import re
import string
import sys

import sqlite3

from optparse import OptionParser, OptionGroup
from subprocess import call

def setupOptions():
    usage = 'usage: %prog [options]'
    parser = OptionParser(usage=usage)

    locGroup = OptionGroup(parser, "Locations", "Where is your git-root and your trac export?")
    locGroup.add_option('--git-root', action='store', dest='git_root_dir',
                        metavar='/GIT/ROOT/DIR',
                        help='Specify the full path to the root of the git-repository that is our destination')
    locGroup.add_option('--trac-export', action='store', dest='trac_export',
                        metavar='/PATH/TO/EXPORTFILE',
                        help='Specify the full path of the Trac sqlite3 database export file')
    parser.add_option_group(locGroup)

    authGroup = OptionGroup(parser, "Authors", "Where can we find information about authors?")
    authGroup.add_option('--author-map', action='store', dest='author_map',
                         metavar='/PATH/TO/AUTHORMAP',
                         help='Specify the full path to the trac-author;git-author CSV to be used to match Trac contribnutors to their git equivalents')
    authGroup.add_option('--extract-trac-authors',
                         action='store_true', dest='extract_authors', default=False,
                         help='Write a list of Trac contributors to stdout, to be used to build the --author-map')
    parser.add_option_group(authGroup)

    defaultGroup = OptionGroup(parser, "Defaults", "What do we use if Trac doesn't have info we need?")
    defaultGroup.add_option('--default-comment', action='store', dest='default_comment',
                            metavar='"COMMENT"',
                            default='Initial load from Trac',
                            help='Specify the git-commit message to use if a given Trac wiki version has no comment')
    defaultGroup.add_option('--default-email-host', action='store', dest='default_host',
                            metavar='example.com',
                            default='localhost',
                            help='Specify the email host to use, if a given Trac contributor has no mapped git-author')
    parser.add_option_group(defaultGroup)

    utilGroup = OptionGroup(parser, "Utility")
    utilGroup.add_option('--debug', action='store_true', default=False, dest='debug',
                         help='Log debugging output')
    utilGroup.add_option('--quiet', action='store_true', default=False, dest='quiet',
                         help='Log only errors')
    parser.add_option_group(utilGroup)

    return parser

def setupLogging(opt):
    # determine the logging level
    if opt.debug:
        level = logging.DEBUG
    elif opt.quiet:
        level = logging.ERROR
    else:
        level = logging.INFO
    # configure logging
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
    return

def verifyOptions(opt):
    logging.info('Verifying options...')

    if (options.trac_export is None):
        logging.error('No trac-export specified - exiting...')
        sys.exit(1)

    if (options.extract_authors):
        return 0

    if (options.git_root_dir is None):
        logging.error('No git-root-directory specified - exiting...')
        sys.exit(1)

    return 0

def verifyLocations(opt):
    logging.info('Verifying locations...')
    fail = False

    # Export exists?
    if (not os.path.isfile(opt.trac_export)):
        fail = True
        logging.error('Cannot find trac-export %s!' % opt.trac_export)

    # git-root exists?
    if (not options.extract_authors and not os.path.isdir(opt.git_root_dir)):
        fail = True
        logging.error('Cannot find git-root-dir %s!' % opt.git_root_dir)

    # authmap specified but doesn't exist?
    if (options.author_map is not None and not os.path.isfile(options.author_map)):
        fail = True
        logging.error('Cannot find author-map-file %s!' % opt.git_root_dir)

    if (fail):
        sys.exit(1)

    return 0

def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def generateTracAuthors(opt):
    logging.info('Extracting Trac authors...')

    conn = sqlite3.connect(opt.trac_export)
    for row in conn.execute('SELECT DISTINCT author FROM wiki ORDER BY author'):
        print row[0]
    conn.close()

    return 0

def loadAuthorMap(opt):
    logging.info('Loading author-map...')
    authmap = {}

    if (opt.author_map is None):
        logging.info('...no map specified, generating from DB')
        conn = sqlite3.connect(opt.trac_export)
        authmap = {row[0]:'%s@%s' % (row[0], opt.default_host) for row in conn.execute('SELECT DISTINCT author FROM wiki ORDER BY author')}
    else:
        logging.info('...generating from specified map-file')
        amf = open(opt.author_map, mode='r')
        csvr = csv.reader(amf)
        authmap = {row[0]:row[1] for row in csvr}

    #import pprint
    #logging.debug('...returning map [%s]' % pprint.pformat(authmap))
    return authmap

def _processFilename(opts, name):
    # Get rid of 'magic' characters from potential filename - replace with '_'
    # Magic: [ \:*?"'<>| ]
    name = re.sub(r'[\\\:\*\?"\'<>\| ]', '_', name)
    if (string.find(name, '/') > -1):
        logging.debug('DIR FOUND [%s]' % name)
        # Treat as dir/dir/dir/basename
        dirpath = string.replace(os.path.dirname(name), '/', 'd/')
        d = '%s/%sd' % (opts.git_root_dir, dirpath)
        f = os.path.basename(name)
        logging.debug('...DIR/NAME [%s]/[%s]' % (d, f))
        if (not os.path.exists(d)):
            os.makedirs(d)
        return '%s/%s' % (d, f)
    else:
        return '%s/%s' % (opts.git_root_dir, name)

def processWiki(opts, authors):
    os.chdir(opts.git_root_dir)
    logging.info('Processing the wiki...')
    conn = sqlite3.connect(opts.trac_export)

    # For every version of every file in the wiki...
    for row in conn.execute("select name, version, author, comment, datetime(time/1000000, 'unixepoch'), text from wiki order by name, version"):
        tracname = row[0]
        tracvers = row[1]
        tracauth = row[2]
        comment  = row[3] if row[3] else 'Initial load of version %s of trac-file %s' % (tracvers, tracname)
        tracdate = row[4]
        contents = row[5]

        fname = _processFilename(opts, tracname)
        logging.debug('...working with file [%s]' % fname)
        # Create file with content
        with open(fname, 'w') as f:
            f.truncate()
            f.write(contents.encode('utf-8'))

        # git-add it
        if (call(['git', 'add', fname])):
            logging.error('ERROR at git-add %s!!!' % fname)
            sys.exit(1)

        # git-commit it
        if (call(['git', 'commit',
            '-m', ('"%s"' % comment),
            '--author', ('"%s <%s>"' % (tracauth, authors.get(tracauth))),
            '--date', ('"%s"' % tracdate)])):
            logging.error('ERROR at git-commit %s!!!' % fname)
            sys.exit(1)

    return 0

def cleanup(opt):
    return 0

if __name__ == '__main__':
    parser = setupOptions()
    (options, args) = parser.parse_args()
    setupLogging(options)
    logging.debug('OPTIONS = %s' % options)

    verifyOptions(options)
    verifyLocations(options)

    if (options.extract_authors):
        generateTracAuthors(options)
        sys.exit(0)

    authMap = loadAuthorMap(options)
    processWiki(options, authMap)

