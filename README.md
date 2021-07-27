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
    create  create a new pijul repository
    update  update a repository create with git-pijul
```

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
100%|██████████████████████████████████████████████████████████████████████████████████████████|
10/10 [00:01<00:00,  9.75it/s]

$> git pull
Updating 3fe9285..114b52f
Fast-forward
 README.md    |  4 ++++
 git_pijul.py | 58 ++++++++++++++++++++++++++++++++++------------------------
 2 files changed, 38 insertions(+), 24 deletions(-)
 create mode 100644 README.md
 
$> git pijul update
Using head: 114b52f953f397b1d025eced6ce6646a5a6c4662 (master)
Using base from last update: 3fe9285acbb319959d9bea85abf1f10ae38e4a05
100%|████████████████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00,  4.12it/s]
```
