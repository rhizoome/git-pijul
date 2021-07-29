import os
import re
import sys
from datetime import datetime
from os import environ
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError
from subprocess import run as run
from textwrap import wrap

import click
import toml
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
    run(["git", "clean", "-xdfq", "-e", ".pijul"], check=True)


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


def clone(git_repo):
    run(["git", "clone", git_repo, "."], check=True, stderr=DEVNULL)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def add_recursive():
    for item in Path(".").iterdir():
        if item.name not in [".pijul", ".git", "."]:
            run(["pijul", "add", "-r", bytes(item)], check=True)


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


def get_changes(channel=None):
    cmd = ["pijul", "log", "--hash-only"]
    if channel:
        cmd += ["--channel", channel]
    res = run(cmd, check=True, stdout=PIPE)
    return set(res.stdout.decode("UTF-8").splitlines())


def get_change(hash):
    res = run(["pijul", "change", hash], check=True, stdout=PIPE)
    return res.stdout.decode("UTF-8")


def get_ancestry_path(head, base):
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


def get_show():
    return run(["git", "show", "-s"], check=True, stdout=PIPE).stdout.decode(
        "UTF-8", errors="ignore"
    )


def get_tag(res, tag, line):
    _, found, field = line.partition(f"{tag}:")
    if found:
        res[tag.lower()] = field.strip()
        return True
    return False


def get_rev_list(head, base):
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


def rename(a, b):
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)
    b.rename(a)
    try:
        run(["pijul", "mv", a, b], check=True)
        return True
    except CalledProcessError:
        return False


re_dep = re.compile(r"\d\] ([a-zA-Z0-9]{53})\b")


def find_dependencies(not_in=None):
    dep_dict = dict()
    changes = get_changes()
    if not_in:
        changes -= get_changes(not_in)
    for change_hash in changes:
        change = get_change(change_hash)
        in_block = False
        dependencies = []
        toml_lines = []
        for line in change.splitlines():
            if in_block:
                if not line.split():
                    break
                split = re_dep.findall(line)
                if split:
                    dependencies.append(split[0])
            elif line.startswith("# Dependencies"):
                in_block = True
            elif line.startswith("# Hunks"):
                break
            else:
                toml_lines.append(line)
        toml_code = os.linesep.join(toml_lines)
        info = toml.loads(toml_code)
        info["hash"] = change_hash
        info["dependencies"] = dependencies
        dep_dict[change_hash] = info
    return dep_dict


re_rev = re.compile(r"\bin_[A-Fa-f0-9]{40}\b", re.MULTILINE)


def find_shortest_path(head):
    res = []
    channels = get_channels()
    for base in re_rev.findall(channels):
        _, _, base = base.partition("_")
        length = len(get_ancestry_path(head, base))
        res.append((length, head, base))
    res = sorted(res, key=lambda x: x[0])
    return res[0]


re_commit = re.compile(r"\bcommit [A-Fa-f0-9]{40}\b", re.MULTILINE)


def extract_subject(msg):
    for line in msg.splitlines():
        line = line.strip()
        if not line or re_commit.match(line):
            continue
        line = "\\n".join(wrap(line, 40))
        return line
    return "no message"


def plot_nodes(deps):
    res = []
    for item in deps.values():
        hash = item["hash"]
        msg = extract_subject(item["message"])
        res.append(f'"{hash}" [ label = "{msg}" ];')
    return os.linesep.join(res)


def plot_edges(deps):
    res = []
    for item in deps.values():
        for dep in item["dependencies"]:
            if dep in deps:
                start = item["hash"]
                res.append(f'"{start}" -> "{dep}";')
    return os.linesep.join(res)


def plot_digraph(not_in=None, rank_lr=True):
    deps = find_dependencies(not_in)
    if rank_lr:
        rank = "rankdir=LR;"
    else:
        rank = ""
    return """
digraph {{
{rank}
{nodes}
{edges}
}}
""".format(
        rank=rank, nodes=plot_nodes(deps), edges=plot_edges(deps)
    )


def prepare_workdir(workdir, tmp_dir):
    os.chdir(bytes(tmp_dir.path))
    clone(workdir)
    Path(".pijul").symlink_to(Path(workdir, ".pijul"))


def run_it(head, base):
    revs = get_rev_list(head, base)
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
        log = get_show()
        log, author, date = parse_log(log)
        timestamp = str(int(date.timestamp()))
        return log, author, timestamp

    def step(self, prev, rev):
        log, author, timestamp = self.prepare(prev, rev)
        add_recursive()
        out, err = record(log, author, timestamp)
        _, _, hash_ = out.partition("Hash:")
        hash_ = hash_.strip()


@click.group()
def main():
    pass


@main.command()
@click.option(
    "--rank-lr/--no-rank-lr",
    "-h/-v",
    default=True,
    help="Remove changes in than channel",
)
@click.option("--not-in", "-i", default=None, help="Remove changes in than channel")
def plot(not_in, rank_lr):
    """Display current changes as graphviz file (git pijul plot | dot -Txlib)"""
    print(plot_digraph(not_in, rank_lr))


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
        add_recursive()
        record_simple(f"commit {head}")
        final_fork(head)


@main.command()
@click.option(
    "--base", "-b", default=None, help="Update from (commit-ish, default '--root')"
)
@click.option("--head", "-h", default=None, help="Update to (commit-ish, default HEAD)")
def update(base, head):
    """Update a repository created with git-pijul"""
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
@click.option(
    "--base", "-b", default=None, help="Import from (commit-ish, default '--root')"
)
@click.option("--head", "-h", default=None, help="Import to (commit-ish, default HEAD)")
def create(base, head):
    """Create a new pijul repository and import a linear history"""
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
