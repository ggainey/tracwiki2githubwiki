# tracwiki2githubwiki

This tool exists to migrate a Trac wiki to a git repository, preserving history (including authors, dates, and comments)

It requires:

 * A sqlite3 export from the existing Trac instance
 * The 'root name' for said Trac (e.g., `http://fedorahosted.org/spacewalk`)
 * A local git-repository

To use it effectively, one should:

 * Use --extract-trac-authors to extract Trac authors
  * USER: turn into a CSV of "trac-author,github-first github-last <login@email>" format, preserving matching github authors as we can, and submit to --author-map
 * Use --extract-trac-attachments to get the URLs of every Trac attachment
  * USER: wget all into images/ in the root wiki directory so we can find them later

With this information, it will:

 * Extract every version from trac.wiki:
  * Convert special characters in the 'name' field to '_'
  * git add that file
  * git commit -m <trac-comment> --author <authormap.get(trac-author) --date <trac-datetime>
 * rename converted files to <name>.md and commit
 * convert all files from Trac markup to Markdown markup and commit

## What does it convert?

 * Blockquotes
 * Fenced ("code formatted") content
 * "code formatted" inlines
 * Headers
 * Image links
 * Lists
 * Tables

## TO-DOs

 * manpage
 * specfile
 * make everything more Python-y
 * Py3 please

## ATTRIBUTIONS

The _convert() code is based on [SGK's Gist](https://gist.github.com/sgk/1286682), as
informed by modifications made in the following clones:

 * [gazpachpking](https://gist.github.com/gazpachoking/9540849)
 * [andreas-fatal](https://gist.github.com/andreas-fatal/739e1ddf4207a0e5e3c8)
 * [pommi](https://gist.github.com/pommi/fb0858abecaad4b245d6)


