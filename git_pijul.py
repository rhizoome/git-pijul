import os
import re
import sys
from datetime import datetime
from os import environ
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError
from subprocess import run as run

import click
from temppathlib import TemporaryDirectory
from tqdm import tqdm

# TODO
# * shallow-update

batch = dict(environ)
batch["VISUAL"] = "/bin/true"


def change():
    res = run(["pijul", "change"], check=True, stdout=PIPE)
    return res.stdout.decode("UTF-8")


def fork(channel):
    run(["pijul", "fork", channel], check=True)


def fork_internal(channel):
    fork(f"in_{channel}")


def git_restore():
    run(["git", "checkout", "--no-overlay", "-q", "."], check=True)
    run(["git", "clean", "-xdfq", "-e", ".pijul", "-e", ".ignore"], check=True)


def pijul_restore():
    run(["pijul", "reset"], check=True)


def init():
    run(["pijul", "init"], check=True)


def switch(channel):
    run(["pijul", "channel", "switch", channel], check=True, stdout=DEVNULL)


def switch_internal(channel):
    switch(f"in_{channel}")


def delete(channel):
    run(["pijul", "channel", "delete", channel], check=True, stdout=DEVNULL)


def delete_internal(channel):
    delete(f"in_{channel}")


def ancestry_path(head, base):
    res = run(
        ["git", "rev-list", "--ancestry-path", f"{base}..{head}"],
        check=True,
        stdout=PIPE,
    )
    return res.stdout.splitlines()


def get_channels():
    return run(["pijul", "channel"], check=True, stdout=PIPE).stdout.decode("UTF-8")


def get_head():
    res = run(["git", "rev-parse", "HEAD"], check=True, stdout=PIPE)
    head = res.stdout.strip().decode("UTF-")
    res = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=True, stdout=PIPE)
    name = res.stdout.strip().decode("UTF-")
    return head, name


def clone(git_repo):
    run(["git", "clone", git_repo, "."], check=True, stderr=DEVNULL)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def add_recursive():
    run(["pijul", "add", "-r", "."], check=True)


def record(log, author, timestamp):
    res = run(
        [
            "pijul",
            "record",
            "--all",
            "--timestamp",
            timestamp,
            "--author",
            author,
            "--message",
            log,
        ],
        check=True,
        env=batch,
        stdout=PIPE,
        stderr=PIPE,
    )
    return res.stdout.strip().decode("UTF-8"), res.stderr.strip().decode("UTF-8")


def record_simple(log):
    res = run(
        [
            "pijul",
            "record",
            "--all",
            "--message",
            log,
        ],
        check=True,
        env=batch,
        stdout=PIPE,
        stderr=PIPE,
    )
    return res.stdout.strip().decode("UTF-8"), res.stderr.strip().decode("UTF-8")


def get_base(head):
    return (
        run(
            ["git", "rev-list", "--root", "--topo-order", head],
            check=True,
            stdout=PIPE,
        )
        .stdout.splitlines()[-1]
        .decode("UTF-8")
    )


def show():
    return run(["git", "show", "-s"], check=True, stdout=PIPE).stdout.decode(
        "UTF-8", errors="ignore"
    )


def get_tag(res, tag, line):
    _, found, field = line.partition(f"{tag}:")
    if found:
        res[tag.lower()] = field.strip()
        return True
    return False


def parse_date(date):
    return datetime.strptime(" ".join(date.split(" ")[:-1]), "%a %b %d %H:%M:%S %Y")


def parse_log(log):
    out = []
    res = {}
    first = True
    for line in log.splitlines():
        found = False
        for tag in ("Date", "Author"):
            if get_tag(res, tag, line):
                found = True
        if not found:
            if first:
                out.append(line.strip())
                first = False
            else:
                out.append(f"    {line.strip()}")
    return "\n".join(out), res["author"], parse_date(res["date"])


def rev_list(head, base):
    return (
        run(
            [
                "git",
                "rev-list",
                "--topo-order",
                "--ancestry-path",
                "--no-merges",
                f"{base}..{head}",
            ],
            check=True,
            stdout=PIPE,
        )
        .stdout.decode("UTF-8")
        .splitlines()
    ) + [base]


def rename(a, b):
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)
    b.rename(a)
    try:
        run(["pijul", "mv", a, b], check=True)
        return True
    except CalledProcessError:
        return False


class Runner:
    def __init__(self, revs):
        self.revs = revs
        self.here = Path(".").absolute()
        self.error = False

    def run(self):
        prev = [self.revs.pop()]
        rev = self.revs.pop()
        checkout(rev)
        add_recursive()
        with tqdm(total=len(self.revs)) as pbar:
            try:
                while self.revs:
                    self.step(prev[-1], rev)
                    prev.append(rev)
                    rev = self.revs.pop()
                    pbar.update()
                self.step(prev[-1], rev)
            except:  # noqa
                info = f"commit {change()}"
                prev.append(rev)
                for last in reversed(prev):
                    if last in info:
                        fork_internal(last)
                        pijul_restore()
                        switch_internal(last)
                        self.error = True
                        break
                raise

    def prepare(self, prev, rev):
        checkout(rev)
        log = show()
        log, author, date = parse_log(log)
        timestamp = str(int(date.timestamp()))
        return log, author, timestamp

    def step(self, prev, rev):
        log, author, timestamp = self.prepare(prev, rev)
        add_recursive()
        out, err = record(log, author, timestamp)
        _, _, hash_ = out.partition("Hash:")
        hash_ = hash_.strip()


def check_git():
    if not Path(".git").exists():
        raise click.UsageError("Please, use git-pijul in root of git-repository")


def check_init():
    if not Path(".pijul").exists():
        init()
    else:
        raise click.UsageError("'.pijul' already exists, please use 'update'")


def check_head(head):
    if head is None:
        head, name = get_head()
        if not name:
            print(f"Using head: {head}")
        else:
            print(f"Using head: {head} ({name})")
    return head


re_rev = re.compile(r"\bin_[A-Fa-f0-9]{40}\b", re.MULTILINE)


def find_shortest_path(head):
    res = []
    channels = get_channels()
    for base in re_rev.findall(channels):
        _, _, base = base.partition("_")
        length = len(ancestry_path(head, base))
        res.append((length, head, base))
    res = sorted(res, key=lambda x: x[0])
    return res[0]


def prepare_workdir(workdir, tmp_dir):
    os.chdir(bytes(tmp_dir.path))
    clone(workdir)
    Path(".pijul").symlink_to(Path(workdir, ".pijul"))


def add_ignore():
    ignore = Path(".ignore").absolute()
    if ignore.exists():
        with open(bytes(ignore), "r") as f:
            if not ".git" in f.read():
                raise click.UsageError("Please add '.git' to your '.ignore' file")
    else:
        with open(bytes(ignore), "w") as f:
            f.truncate(0)
            f.write(".git\n")


def run_it(head, base):
    add_ignore()
    revs = rev_list(head, base)
    runner = Runner(revs)
    try:
        runner.run()
    except:  # noqa
        if runner.error:
            delete_internal(head)
        raise


def final_fork(head):
    head = head[:7]
    head = f"work_{head}"
    fork(head)
    switch(head)
    print("Please do not work in internal in_* channels\n")
    print("If you like to rename the new work channel call:\n")
    print(f"pijul channel rename {head} $new_name")


@click.group()
def main():
    pass


@main.command()
def shallow():
    """create a new pijul repository from the current revision without history"""
    workdir = Path(".").absolute()
    check_git()
    check_init()
    with TemporaryDirectory() as tmp_dir:
        prepare_workdir(workdir, tmp_dir)
        head, _ = get_head()
        fork_internal(head)
        switch_internal(head)
        add_ignore()
        add_recursive()
        record_simple(f"commit {head}")
        final_fork(head)


@main.command()
@click.option("--base", default=None, help="Update from (commit-ish, default '--root')")
@click.option("--head", default=None, help="Update to (commit-ish, default HEAD)")
def update(base, head):
    """update a repository created with git-pijul"""
    workdir = Path(".").absolute()
    check_git()
    if not Path(".pijul").exists():
        raise click.UsageError("'.pijul' does not exist, please use 'create'")
    if head is None:
        head = check_head(head)
    path = find_shortest_path(head)
    _, new_head, new_base = path
    assert head == new_head
    if base is None:
        base = new_base
        print(f"Using base from previous update: {base}")
    if path[0] == 0:
        print("No updates found")
        sys.exit(0)
    with TemporaryDirectory() as tmp_dir:
        prepare_workdir(workdir, tmp_dir)
        pijul_restore()
        switch_internal(base)
        fork_internal(head)
        switch_internal(head)
        git_restore()
        run_it(head, base)
        final_fork(head)


@main.command()
@click.option("--base", default=None, help="Import from (commit-ish, default '--root')")
@click.option("--head", default=None, help="Import to (commit-ish, default HEAD)")
def create(base, head):
    """create a new pijul repository and import a linear history"""
    workdir = Path(".").absolute()
    check_git()
    check_init()
    head = check_head(head)
    if base is None:
        base = get_base(head)
        print(f"Using base: {base} ('--root')")
    with TemporaryDirectory() as tmp_dir:
        prepare_workdir(workdir, tmp_dir)
        fork_internal(head)
        switch_internal(head)
        run_it(head, base)
        final_fork(head)


if __name__ == "__main__":
    main()
