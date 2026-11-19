# 0008 Static copying and output clearing

Date: 2026-11-18
Status: accepted

## Context

The builder copies static files into, and deletes from, a folder on the user's disk.

## Decision

- Static copying skips symlinks (files and folders), as content loading does (0004),
  and skips `.git` folders inside static. Other dotfiles copy.
- Clearing deletes each top-level entry of the output folder except `.git` and `CNAME`.
  A symlink is unlinked, never followed; `rmtree` is used for real folders only.
- The builder refuses (`ConfigError`) when the resolved output folder is: the
  filesystem root, home, the site root or a parent of it, a folder containing or equal
  to the content, templates, static or data folder, or **inside** one of those (copying
  static into static would recurse). It also refuses a symlink, a non-folder, and a
  folder that is or is inside a `.git` folder (checked first, before touching disk).
- A static `CNAME` overwrites the preserved one; `render()` to `CNAME` is a
  `ContentError`.
- No output, from render or static, may have a `.git` path component at any depth
  (`ContentError`, "reserved path"). Static copying skips every entry named `.git`
  (file, folder or symlink) at any depth and does not count it.
- `copy_static` raises `ContentError` when its source equals, contains, or lies inside
  the output folder.
- Render paths with empty or `.` segments (`a//b/`, `./a/`) are rejected so the page
  URL always equals the written path.
- The 404 page uses root-relative links even with `relative_links = true`, because the
  host serves it at any depth.

## Consequences

- A site that symlinks assets in must copy them.
- A failed build leaves partial output; there is no rollback.
