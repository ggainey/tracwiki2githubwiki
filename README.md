# tracwiki2githubwiki

This tool exists to migrate a Trac wiki to a git repository, preserving history (including authors, dates, and comments)

It requires:

 * A sqlite3 export from the existing Trac instance
 * The 'root name' for said Trac (e.g., `http://fedorahosted.org/spacewalk`)
 * A local git-repository
 * An images/ directory in said repo, full of images extracted from Trac
 * An (optional) author-mapping.csv, of trac-author,"Git Author <gitauthor@email.adr>" format

With this information, it will:

 * Use --extract-trac-authors to extract Trac authors
  * USER: Fill in matching github authors as we can, submit to --author-map
 * Use --extract-trac-attachments to get the URLs of every Trac attachment
  * USER: wget all into images/ in the root wiki directory so we can find them later
 * Extract every version from trac.wiki:
  * Convert special characters in the 'name' field to '_'
  * git add that file
  * git commit -m <trac-comment> --author <authormap.get(trac-author) --date <trac-datetime>
 * rename converted files to <name>.md and commit
 * convert all files from Trac markup to Markdown markup and commit

## What does it convert?

 * Headers
 * Lists
 * Blockquotes
 * Fenced content
 * Image links

## TO-DOs

 * tables? (ew)
 * manpage
 * specfile
 * make everything more Python-y
 * Py3?
