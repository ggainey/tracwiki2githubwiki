# tracwiki2githubwiki

This tool exists to migrate a Trac wiki to a git repository, preserving history (including authors, dates, and comments)

It requires:

 * A sqlite3 export from the existing Trac instance
 * A local git-repository
 * An (optional) author-mapping.csv, of trac-author,"Git Author <gitauthor@email.adr>" format

With this information, it will:

 * Extract every version from trac.wiki
 * Convert special cahracters in the 'name' field to '_'
 * Treat names with / as directory-paths
 * Create any needed directory paths
 * Create a file under git-root with the 'basename' of the name-filed, and the contents of that version
 * git add that file
 * git commit -m <trac-comment> --author <authormap.get(trac-author) --date <trac-datetime>
 * TODO: convert all files from Trac markup to Markdown markup
 * TODO: rename converted files to <name>.md
 * TODO: commit results

## TO-DOs

 * Trac-to-Markdown phase
 * Reconsider the treatment of pseudo-directories pbased on Trac filenames
  * Leave directories with their actual names, files with same name as directory become index-file in that directory?
 * manpage
 * specfile
 * make everything more Python-y
 * Py3?
