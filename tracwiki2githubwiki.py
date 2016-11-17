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
tracwiki2githubwiki - a tool for transforming a Trac wiki, as contained in an exported
sqlite3 database, into a github-wiki git repository
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

ALLVERSIONS_SQL = '''
select name, version, author, comment, datetime(time/1000000, 'unixepoch') fixeddate, text
  from wiki
 order by name, version
'''

MAXVERSION_SQL = '''
select name, version, text
  from wiki w
 where version = (select max(version) from wiki where name = w.name)
 order by name
'''

GETAUTHOR_SQL = '''
select distinct author
  from wiki
 order by author
'''

MOVE_COMMENT    = "Renaming all files to have .md extension"
CONVERT_COMMENT = "Converted to Markdown by tracwiki2githubwiki"

# Map of <tracname>: fsname - used in many places
allfiles = {}
alldirs = set()


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

def generateTracAuthors(opt):
    logging.info('Extracting Trac authors...')

    conn = _connect(opt)
    for row in conn.execute(GETAUTHOR_SQL):
        print row['author']
    conn.close()

    return 0

def loadAuthorMap(opt):
    logging.info('Loading author-map...')
    authmap = {}

    if (opt.author_map is None):
        logging.info('...no map specified, generating from DB')
        conn = _connect(opt)
        authmap = {row['author']:'%s@%s' % (row['author'], opt.default_host) for row in conn.execute(GETAUTHOR_SQL)}
        conn.close()
    else:
        logging.info('...generating from specified map-file')
        # Load authmap from CSV
        with open(opt.author_map, mode='r') as amf:
            csvr = csv.reader(amf)
            authmap = {row[0]:row[1] for row in csvr}
        # Fill in any missing authors
        for k in authmap.keys():
            if (not authmap[k]):
                authmap[k] = '%s@%s' % (k, opt.default_host)

    #import pprint
    #logging.debug('...returning map [%s]' % pprint.pformat(authmap))
    return authmap

def _cleanseFilename(name):
    """
    Get rid of 'magic' characters from potential filename - replace with '_'
    Magic: [ \:*?"'<>| ]
    """
    return re.sub(r'[\\\:\*\?"\'<>\| ]', '_', name)

def _processFilename(opts, name, dirs):
    """
    Handle directories, and files with the same name as directories
    If name is foo/bar, and bar is in dirs (meaning there is a foo/bar/blech somewhere),
    then we create the path foo/bar and the filename foo/bar/Index
    """
    name = _cleanseFilename(name)

    # Some dir/filename collisions happen at top-level :(
    if (name in dirs):
        name = name + '/Index'

    if (string.find(name, '/') > -1):
        #logging.debug('DIR FOUND [%s]' % name)
        # Treat as dir/dir/dir/basename
        d = os.path.dirname(name)
        f = os.path.basename(name)
        if (f in dirs):
            #logging.debug('...FILENAME IS A DIR! [' + f + ']')
            d = d + '/' + f
            f = 'Index'
        #logging.debug('...DIR/NAME [%s]/[%s]' % (d, f))
        # We're about to work with the FILESYSTEM - don't forget git-root!
        if (not os.path.exists(opts.git_root_dir + '/' + d)):
            os.makedirs(opts.git_root_dir + '/' + d)
        return '%s/%s' % (d, f)
    else:
        return name

def _skipFile(fname):
    return (fname.startswith('Trac') or (fname.startswith('Wiki') and not fname.startswith('WikiStart')))

def _connect(opt):
    conn = sqlite3.connect(opt.trac_export)
    conn.row_factory = sqlite3.Row
    return conn

def createFilenameMapping(opt):
    alldirs = set()
    logging.info('Creating filename-mapping...')
    conn = _connect(opt)

    # First find all directories
    for row in conn.execute(MAXVERSION_SQL):
        name = _cleanseFilename(row['name'])
        if (string.find(name, '/') > -1):
            dirs = os.path.dirname(name).split('/')
            alldirs |= set(dirs)

    import pprint
    logging.debug('...created alldirs [%s]' % pprint.pformat(alldirs))

    # Now, create a dict of (tracname: possibly-renamed-but-definitely-fqdn)
    for row in conn.execute(MAXVERSION_SQL):
        name = _processFilename(opt, row['name'], alldirs)
        allfiles[_cleanseFilename(row['name'])] = name

    conn.close()

    logging.debug('...created dict [%s]' % pprint.pformat(allfiles))

def processWiki(opts, authors):
    logging.info('Processing the wiki...')
    os.chdir(opts.git_root_dir)
    conn = _connect(opts)

    # For every version of every file in the wiki...
    for row in conn.execute(ALLVERSIONS_SQL):
        if (_skipFile(row['name'])):
            continue

        comment  = row['comment'] if row['comment'] else 'Initial load of version %s of trac-file %s' % (row['version'], row['name'])

        fname = opts.git_root_dir + '/' + allfiles[_cleanseFilename(row['name'])]
        logging.debug('...working with file [%s]' % fname)
        #logging.debug('tracname|fname : %s|%s' % (row['name'], fname))

        # Create file with content
        with open(fname, 'w') as f:
            f.truncate()
            f.write(row['text'].encode('utf-8'))

        # git-add it
        if (call(['git', 'add', fname])):
            logging.error('ERROR at git-add %s!!!' % fname)
            sys.exit(1)

        # git-commit it
        if (call(['git', 'commit',
            '-m', ('"%s"' % comment),
            '--author', ('"%s <%s>"' % (row['author'].encode('utf-8'), authors.get(row['author']))),
            '--date', ('"%s"' % row['fixeddate'])])):
            logging.error('ERROR at git-commit %s!!!' % fname)
            sys.exit(1)

    conn.close()
    return 0

def _convert_wiki_link(link):
    """
    <tracname>
    <tracname>#anchor
    wiki:<tracname> or just <tracname>
    wiki:<tracname>#anchor
    http<s>://foobarblech?pi=1&p3=4
    """
    #logging.debug('..._convert_wiki_link [' + link + ']')
    if (link.startswith('http')):
        return link
    else:
        # drop leading wiki:
        link = link[5:] if link.startswith('wiki:') else link
        # find and drop any anchors
        lasthash = string.rfind(link, '#')
        if (lasthash > -1):
            link = link[:lasthash]
        # Cleanse the result
        link = _cleanseFilename(link)
        # See if what's left might now be recognized as a directory
        if (os.path.basename(link) in alldirs):
            link += '/Index'

    #logging.debug('..._convert_wiki_link about to look for [' + link + ']')

    # Final result might *still* not be in allfiles (because broken links are a thing...)
    if (link in allfiles):
        return allfiles[link]
    else:
        return link

# Fixing Trac links is fun, esp when you're doing multiple passes.
# [ThisIsMyLink And its description] wants to become (And its description)[ThisIsMyLink]
# Unfortunately, that leaves [ThisIsMyLink] looking like a 'simple Trac link' that can be
# picked up by further REs. Fun.
# We will use '}}' in place of '[', so we stop trying to 'fix' it, and then globally replace
# it at the end of processing.
def sub_full_wiki_link(m):
    #logging.debug('...sub_full,[%s](%s)' % (m.group(2), m.group(1)))
    return '}]}%s](%s)' % (m.group(2), _convert_wiki_link(m.group(1)))

def sub_simple_wiki_link(m):
    #logging.debug('...sub_simple, [[%s]]' % m.group(1))
    return '}]}[%s]]' % _convert_wiki_link(m.group(1))

def _looks_like_blockquote(line):
    """
    4 starting blanks is a blockquote - except when it starts a line
    that is a header or part of a bullet-list (?!?)
    """
    if (line.startswith('    ')):
        line = line.strip()
        if (not line):
            return True
        leadchar = line[0] # Check lead non-whitespace char
        return False if (leadchar == '*' or leadchar == '=') else True
    else:
        return False

def _convert(text):
    """
    Conversion rules taken from https://gist.github.com/sgk/1286682, as modified by several
    other clones thereof
    """
    # Fix 'Windows EOL' to 'Linux EOL'
    text = re.sub('\r\n', '\n', text)
    # Fix code-format-inline
    text = re.sub(r'{{{(.*?)}}}', r'`\1`', text)
    # Fix fenced-block
    def indent4(m):
        return '\n    ' + m.group(1).replace('\n', '\n    ')
    # Fix code-format-block
    text = re.sub(r'(?sm){{{\n(.*?)\n}}}', indent4, text)
    # Remove [[TOC]]
    text = re.sub(r'\[\[TOC.*\]\]', r'', text)
    # Remove [[PageOutline]]
    text = re.sub(r'\[\[PageOutline\]\]', r'', text)
    # Headers (note: can look like '== Foo == #fooanchor and stuff' in Trac)
    # Fix Header-4
    text = re.sub(r'(?m)^\s*====\s+(.*?)\s+====([\s#].*)$', r'#### \1\n\2\n', text)
    # Fix Header-3
    text = re.sub(r'(?m)^\s*===\s+(.*?)\s+===([\s#].*)$', r'### \1\n\2\n', text)
    # Fix Header-2
    text = re.sub(r'(?m)^\s*==\s+(.*?)\s+==([\s#].*)$', r'## \1\n\2\n', text)
    # Fix Header-1
    text = re.sub(r'(?m)^\s*=\s+(.*?)\s+=([\s#].*)$', r'# \1\n\2\n', text)
    # Fix 4th-level-bullet-lists
    text = re.sub(r'^        * ', r'****', text)
    text = re.sub(r'^       * ', r'****', text)
    # Fix 3rd-level-bullet-lists
    text = re.sub(r'^      * ', r'***', text)
    text = re.sub(r'^     * ', r'***', text)
    # Fix 2nd-level-bullet-lists
    text = re.sub(r'^    * ', r'**', text)
    text = re.sub(r'^   * ', r'**', text)
    # Fix bullet-lists
    text = re.sub(r'^  * ', r'*', text)
    text = re.sub(r'^ * ', r'*', text)
    # Fix numbered lists
    text = re.sub(r'^ \d+. ', r'1.', text)
    # Fix hard-BR
    text = re.sub(r'(?m)\[\[BR\]\]$', '\n', text)
    a = []
    for line in text.split('\n'):
        # Ignore blockquote lines
        if (not _looks_like_blockquote(line)):
            # Fix simple-internal-wiki-links (?)
            line = re.sub(r'(?<!\[)\[([^\s\[\]]+?)\]', sub_simple_wiki_link, line)
            # Fix complex-internal-wiki-links
            line = re.sub(r'\[wiki:([^\s\[\]\"]+)\s([^\[\]]+)\]', sub_full_wiki_link, line)
            # Fix complex-internal-wiki-links WITH QUOTES
            line = re.sub(r'\[wiki:"([^\[\]]+)"\s([^\[\]]+)\]', sub_full_wiki_link, line)
            # Fix wiki-links that don't start with wiki:
            line = re.sub(r'\[([^\s\[\]]+)\s([^\[\]]+)\]', sub_full_wiki_link, line)
            # Fix "don't auto-trac-link-this" links
            line = re.sub(r'\!(([A-Z][a-z0-9]+){2,})', r'\1', line)
            # Fix bold
            line = re.sub(r'\'\'\'(.*?)\'\'\'', r'*\1*', line)
            # Fix italics
            line = re.sub(r'\'\'(.*?)\'\'', r'_\1_', line)
            # Fix the LEAVE-ME-ALONE special sequence to [
            line = line.replace('}]}', '[')
        a.append(line)
    text = '\n'.join(a)
    return text

def renameCurrent(opts):
    """
    We're going to do ONE commit that renames All The Things to *.md
    """

    logging.info('Renaming all to *.md...')
    os.chdir(opts.git_root_dir)

    conn = _connect(opts)
    # For every every file in the wiki, get the max-version, rename to *.md
    for row in conn.execute(MAXVERSION_SQL):
        if (_skipFile(row['name'])):
            continue

        fname = opts.git_root_dir + '/' + allfiles[_cleanseFilename(row['name'])]
        fname_md = fname + '.md'

        # git-mv the file to give it the .md extension
        rc = call(['git', 'mv', fname, fname_md])
        if (rc):
            logging.error('ERROR [%d] at git-mv %s!!!' % (rc, fname))
            continue

    # git-commit ALL THE THINGS
    rc = call(['git', 'commit', '-m', ('%s' % MOVE_COMMENT)])
    if (rc):
        logging.error('ERROR [%d] at MOVE git-commit!!!' % rc)

    conn.close()
    return rc

def toMarkdown(opts):
    """
    Convert Trac-markup in most-recent version of files, which have been renamed to *.md,
    to Markdown markup
    We do ONE COMMIT that commits all the markup-conversion changes
    """
    logging.info('Converting to markdown...')
    os.chdir(opts.git_root_dir)

    conn = _connect(opts)
    # For every every file in the wiki, get the max-version, convert that text to
    # markdown, and save it as a new version of that file
    for row in conn.execute(MAXVERSION_SQL):
        if (_skipFile(row['name'])):
            continue

        # CONVERT THE CONTENT
        content = _convert(row['text'])

        fname = opts.git_root_dir + '/' + allfiles[_cleanseFilename(row['name'])]
        fname_md = fname + '.md'
        # Write the new contents
        logging.debug('...writing converted file [%s]' % fname_md)
        with open(fname_md, 'w') as f:
            f.truncate()
            f.write(content.encode('utf-8'))

        # git-add the new contents
        rc = call(['git', 'add', fname_md])
        if (rc):
            logging.error('ERROR [%d] at git-add %s!!!' % (rc, fname_md))
            continue

    # git-commit ALL THE THINGS
    rc = call(['git', 'commit', '-m', ('%s' % CONVERT_COMMENT)])
    if (rc):
        logging.error('ERROR [%d] at git-commit %s!!!' % (rc, fname))

    conn.close()
    return rc

def processAttachments(opts, authors):
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
    createFilenameMapping(options)
    processWiki(options, authMap)
    renameCurrent(options)
    toMarkdown(options)
    processAttachments(options, authMap)
