# The old do.py generators (2020–21)

Read 2026-11-18: [svata](https://github.com/mojzis/svata),
[data-o-klimatu](https://github.com/mojzis/data-o-klimatu),
[zemreli-kvuli-covidu](https://github.com/mojzis/zemreli-kvuli-covidu) and the private
`lajf`. `tiddly` and `twitter_collections` are empty on GitHub.

## How they worked

- A ~100-line `do.py` with click commands, copied between repos. svata: `publish`, `add FILENAME URL`. Notebook sites: `pub`. lajf: `pub`, `newday`.
- No settings. Hard-coded folders: `sources/<kind>/*.md`, `templates/`, `public/`, and a cache folder (`data/{meta,ogimg,thumb}`, `work/`). Folders had to exist already.
- The loader turned each markdown file into a dict:
  ```python
  for item in sorted(glob, reverse=True):
      matter = frontmatter.load(item)
      data = dict(matter)
      data['body'] = md(matter.content)
      data['filename'] = pathlib.Path(item).stem
  ```
  lajf also took the title from the first `<h1>`, falling back to the file name.
- One template per page into `public/<slug>.html`, then an index from the whole list. lajf passed every page to each page for a sidebar.
- `base.html` blocks: `title`, `customhead`, `bodyscript`, `uppernav`, `content` (zemreli adds `ogtitle`, `ogimage`). Child templates inline their CSS.
- Notebooks: exported by hand with nbconvert, title scraped with a regex ("a bit too fragile"), OG image found by convention at `notebooks/<name>/ogimg.png`, 200x100 thumbnails for the index.
- svata's nicest bit: `add` scaffolds from `TEMPLATE.md`; `publish` fetches each link's Open Graph data, caches it as JSON, downloads `og:image`, makes a 100x100 thumbnail only if missing. CI keeps the cache between runs.

## The head

- Had: charset, title, Plausible with the domain typed in. zemreli alone: `twitter:card`, og:title, og:description, description, og:image (absolute URL typed in), the same description on every page.
- Missing everywhere: viewport, canonical, og:url, og:type, og:site_name, og:locale, image size, per-page descriptions, favicon (on every README todo list), sitemap, robots, RSS, 404.
- Bugs: autoescape off by accident, relative URLs, `static/` never copied.

## The original deedum plan

From lajf `sources/ideas/simple_static_generator.md`, quoted in full:

```
# Simple Static Generator

take the codes in the past few projects and try to abstract it
- nice logging
- class structure
- scaffolding
- deployment with github & netlify
- settings & directories (in the twitter project)

## steps
- learn the module structure (from click ?)
- figure out structure of code

what will new projects using it look like
boilerplate do.py with commands ? vs calling the module and it searching for overrides ?

App class with methods that will be implementing the commands and overriding the parent from the module

## new features

- deployment with https://pypi.org/project/pynetlify/
 - + secret settings
- rss (?)
- change log ?
- local serving (+change detection ?)
 - python -m http.server (invoke from code maybe ?)
- i18n

deedum org
deedum project

dd-boilerplate
dd-deploy-netlify (plugin - come up with ways to do plugins ...)

## settings
- netlify site id (actually a netlify plugin setting :)
- plausible (plugin ? :)
```

README todo lists add: favicon, "google stuff/setup", og image, footer, about page, date published, GitHub Action, date of generation.

## Keep

- Small enough to read in one sitting.
- Folder conventions instead of config.
- A page is a dict: frontmatter plus `body`, `slug`, `title`.
- Every template extends one base and fills a few blocks.
- Scaffolding a new entry from a template file (`add`, `newday`).
- Images found by naming convention.
- Cache anything fetched from the network.

## Drop

- Copy-pasted loaders, regex title scraping, domains typed into templates, autoescape off, folders made by hand, notebooks exported by hand.
