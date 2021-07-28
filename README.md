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
Using head: 3bc7b1e8618681d4e3069989160998f7d366f08c (HEAD)
Using base: b215e32b5d60eb19a0676a2b9072ac7a352e1c50 ('--root')
100%|███████████████████████████████████████████████|
29/29 [00:02<00:00, 10.17it/s]
Please do not work in internal in_* channels

If you like to rename the new work channel call:

pijul channel rename work_3bc7b1e $new_name

$> pijul channel
  in_3bc7b1e8618681d4e3069989160998f7d366f08c
  main
* work_3bc7b1e

$> git pull
Updating 3bc7b1e..7ec741d
Fast-forward
 README.md      |  2 +-
 git_pijul.py   | 50 ++++++++++++++++++++++++++++++++++++++------------
 pyproject.toml |  2 +-
 3 files changed, 40 insertions(+), 14 deletions(-)
 
$> git pijul update
Using head: 7ec741d2e7b8c5c0ef7302d47e1b8af04c14b54d (master)
Using base from previous update: 3bc7b1e8618681d4e3069989160998f7d366f08c
100%|███████████████████████████████████████████████| 1/1 [00:00<00:00,  8.20it/s]
Please do not work in internal in_* channels

If you like to rename the new work channel call:

pijul channel rename work_7ec741d $new_name

$> pijul channel
  in_3bc7b1e8618681d4e3069989160998f7d366f08c
  in_7ec741d2e7b8c5c0ef7302d47e1b8af04c14b54d
  main
  work_3bc7b1e
* work_7ec741d
```

changes
-------

### 0.3.0

* 0.3.0 git-pijul now creates a work and an internal channel. The internal
  channel should not be used by the user. I think this is the first step to allow
  back-sync.

### 0.4.0

* stop using .ignore, instead add root directory items one by one, ignoring .git

### 0.5.0

* allow to plot changes with `git pijul plot | dot -Txlib`
