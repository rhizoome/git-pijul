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
  create            Create a new pijul repository and import a linear...
  plot              Display current changes as graphviz file (git pijul...
  set-diff          Difference between two sets of changes of channels.
  set-intersection  Intersection between two sets of changes of channels.
  set-union         Union changes of channels.
  shallow           create a new pijul repository from the current...
  update            Update a repository created with git-pijul
```

`git-pijul create` finds an ancestry-path with `git rev-list --ancestry-path
--no-merges --topo-order`. It will then checkout each revision into a temp
directory and add it to pijul. Non-linear history is dropped. The last
revision/patchset will be forked into a channel.

`git-pijul update` finds in git the shortest path from the current git-revision
to a existing channel and updates pijul from that channel.

`git-pijul shallow` create a new pijul repository from the current revision without
history.

`git-pijul plot` plots dependencies of all changes, with `-i` you can exclude changes from a
channel, usually the `main` channel that contains published changes. This allows
you to select the changes you want to publish.

There are also set opertions on sets of changes in channels. Typical usage is
applying changes after a `git pijul update`:

```bash
git pijul set-diff -l  work_9189af5 | xargs pijul apply
```

example
-------

```console
$> git clone https://github.com/ganwell/git-pijul
Cloning into 'git-pijul'...
remote: Enumerating objects: .....

$> cd git-pijul

$> git pijul create --name upsteam01
Using head: e75db07f2b56b1a836f3841808b188ea8e642ba1 (HEAD)
Using base: b215e32b5d60eb19a0676a2b9072ac7a352e1c50 ('--root')
100%|█████████████████████████████████████| 40/40 [00:03<00:00, 12.40it/s]
Please do not modify the in_* channels

To get the latest changes call:

git pijul set-diff -l upstream01 | xargs pijul apply

$> git pijul set-diff -l upstream01 | xargs pijul apply
Outputting repository ↖

$> pijul channel
  in_e75db07f2b56b1a836f3841808b188ea8e642ba1
* main
  upstream01

$> git pull
Updating 3bc7b1e..7ec741d
Fast-forward
 README.md      |  2 +-
 git_pijul.py   | 50 ++++++++++++++++++++++++++++++++++++++------------
 pyproject.toml |  2 +-
 3 files changed, 40 insertions(+), 14 deletions(-)

$> git pijul update --name upstream02
Using head: 2386120d310e65ea38110059fc427c106a75a58a (master)
Using base from previous update: e75db07f2b56b1a836f3841808b188ea8e642ba1
100%|█████████████████████████████████████| 7/7 [00:00<00:00,  7.62it/s]
Please do not modify the in_* channels

To get the latest changes call:

git pijul set-diff -l upstream02 | xargs pijul apply

$> git pijul set-diff -l upstream02 | xargs pijul apply
Outputting repository ↖

$> pijul channel
  in_e75db07f2b56b1a836f3841808b188ea8e642ba1
  in_2386120d310e65ea38110059fc427c106a75a58a
* main
  upstream01
  upstream02
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

### 0.6.0

* `git-pijul plot` plots dependencies of all changes, with `-i` you can exclude changes from a
  channel, usually the `main` channel that contains published changes. This allows
  you to select the changes you want to publish.

### 0.7.0

* add set operations on changes in channels

### 0.8.0

* do not switch channels, use --channel for all operations
