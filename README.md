git-pijul
=========

update pijul from git.

install
-------

```bash
pip install git-pijul
```

usage
-----

```text
Usage: git-pijul [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  create   create a new pijul repository and import a linear history
  shallow  create a new pijul repository from the current revision without...
  update   update a repository created with git-pijul
```

`git-pijul create` finds an ancestry-path with `git rev-list --ancestry-path
--no-merges --topo-order`. It will then checkout each revision into a temp
directory and add it to pijul. Non-linear history is dropped. The last
revision/patchset will be forked into a channel.

`git-pijul update` finds in git the shortest path from the current git-revision
to a existing channel and updates pijul from that channel.

`git-pijul shallow` create a new pijul repository from the current revision without
history.

example
-------

```console
$> git clone https://github.com/ganwell/git-pijul
Cloning into 'git-pijul'...
remote: Enumerating objects: 49, done.
remote: Counting objects: 100% (49/49), done.
remote: Compressing objects: 100% (22/22), done.
remote: Total 49 (delta 24), reused 49 (delta 24), pack-reused 0
Receiving objects: 100% (49/49), 44.34 KiB | 1.93 MiB/s, done.
Resolving deltas: 100% (24/24), done.

$> cd git-pijul

$> git pijul create
Using head: 3fe9285acbb319959d9bea85abf1f10ae38e4a05 (master)
Using base: b215e32b5d60eb19a0676a2b9072ac7a352e1c50 ('--root')
100%|███████████████████████████████████████████████| 10/10 [00:01<00:00,  9.75it/s]

$> pijul channel
* 3fe9285acbb319959d9bea85abf1f10ae38e4a05
  main

$> git pull
Updating 3fe9285..114b52f
Fast-forward
 README.md    |  4 ++++
 git_pijul.py | 58 ++++++++++++++++++++++++++++++++++------------------------
 2 files changed, 38 insertions(+), 24 deletions(-)
 create mode 100644 README.md
 
$> git pijul update
Using head: 114b52f953f397b1d025eced6ce6646a5a6c4662 (master)
Using base from previous update: 3fe9285acbb319959d9bea85abf1f10ae38e4a05
100%|███████████████████████████████████████████████| 1/1 [00:00<00:00,  4.12it/s]

$> pijul channel
* 114b52f953f397b1d025eced6ce6646a5a6c4662
  3fe9285acbb319959d9bea85abf1f10ae38e4a05
  main

```
