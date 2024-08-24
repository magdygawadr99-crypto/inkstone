---
title: dotfiles
description: Shell, editor and git configuration, plus the script that installs them.
weight: 30
tags: [shell]
---

Everybody has one of these. Mine is notable only for its restraint: one
`install.sh` that symlinks eleven files and refuses to overwrite anything it
did not create.

The part other people have found useful is the git configuration, in
particular three aliases I could no longer work without:

```ini
[alias]
    # what did I do today
    today = log --since=midnight --author='Magdy' --oneline
    # undo the last commit but keep the changes
    uncommit = reset --soft HEAD~1
    # branches, most recently used first
    recent = branch --sort=-committerdate --format='%(committerdate:relative)%09%(refname:short)'
```

No plugin manager, no framework, no prompt that takes 400 ms to draw.
