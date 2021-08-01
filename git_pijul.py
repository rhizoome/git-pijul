import os
import re
import sys
from datetime import datetime
from os import environ
from pathlib import Path
from subprocess import DEVNULL, PIPE
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


def do_apply(changes):
    run(["pijul", "apply"] + changes, check=True, stdout=DEVNULL)


def new(name):
    run(["pijul", "channel", "new", f"in_{name}"], check=True)


def delete(name):
    run(["pijul", "channel", "delete", f"in_{name}"], check=True)


def rename(from_, to_):
    # Workaround rename switches to channel, what we don't want
    fork(from_, to_)
    delete(from_)


def alias(channel, name):
    run(["pijul", "fork", "--channel", f"in_{channel}", name], check=True)


def fork(channel, name):
    run(["pijul", "fork", "--channel", f"in_{channel}", f"in_{name}"], check=True)


def git_restore():
    run(["git", "checkout", "--no-overlay", "-q", "."], check=True)
    run(["git", "clean", "-xdfq", "-e", ".pijul"], check=True)


def pijul_restore():
    run(["pijul", "reset"], check=True)


def init():
    run(["pijul", "init"], check=True)


def delete(channel):
    run(["pijul", "channel", "delete", f"in_{channel}"], check=True, stdout=DEVNULL)


def clone(git_repo):
    run(["git", "clone", git_repo, "."], check=True, stderr=DEVNULL)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def add_recursive():
    for item in Path(".").iterdir():
        if item.name not in [".pijul", ".git", "."]:
            run(["pijul", "add", "-r", bytes(item)], check=True)


def record(channel, log, author, timestamp):
    res = run(
        [
            "pijul",
            "record",
            "--all",
            "--channel",
            f"in_{channel}",
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


def record_simple(channel, log):
    res = run(
        [
            "pijul",
            "record",
            "--all",
            "--channel",
            f"in_{channel}",
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


def find_current_channel():
    channels = get_channels().splitlines()
    for channel in channels:
        if channel.startswith("* "):
            _, _, result = channel.partition("* ")
            return result
    raise click.UsageError("No current pijul channel??")


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


def run_it(head, base, name):
    revs = get_rev_list(head, base)
    runner = Runner(revs, head, base)
    runner.run()
    if name:
        alias(head, name)
        final_message(name)
    else:
        final_message(f"in_{head}")


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
    def __init__(self, revs, head, base):
        self.revs = revs
        self.here = Path(".").absolute()
        self.head = head
        self.base = base

    def run(self):
        prev = self.revs.pop()
        rev = self.revs.pop()
        checkout(rev)
        add_recursive()
        with tqdm(total=len(self.revs)) as pbar:
            try:
                while self.revs:
                    self.step(prev, rev)
                    prev = rev
                    rev = self.revs.pop()
                    pbar.update()
                self.step(prev, rev)
            except:
                rename(self.head, prev)
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
        record(self.head, log, author, timestamp)


def fill_channel_sets(left, right):
    if not left:
        left = [find_current_channel()]
    if not right:
        right = [find_current_channel()]
    left_set = set()
    for item in left:
        left_set.update(get_changes(item))
    right_set = set()
    for item in right:
        right_set.update(get_changes(item))
    return left_set, right_set


def final_message(head):
    print("Please do not modify the in_* channels\n")
    print("To get the latest changes call:\n")
    print(f"git pijul apply {head}")


@click.group()
def main():
    pass


@main.command()
@click.argument("channel")
def apply(channel):
    """Apply all changes from CHANNEL iteratively"""
    left_set, right_set = fill_channel_sets([channel], [])
    result = left_set - right_set
    total = len(result)
    with tqdm(total=total) as pbar:
        while left_set:
            changes = list(left_set)[:50]
            do_apply(changes)
            left_set, right_set = fill_channel_sets([channel], [])
            result = left_set - right_set
            l = len(result)
            done = total - l
            total = l
            pbar.update(done)


@main.command()
@click.option(
    "--left", "-l", multiple=True, help="Left channel, multiple options allowed"
)
@click.option(
    "--right", "-r", multiple=True, help="Right channel, multiple options allowed"
)
def set_diff(left, right):
    """Difference between two sets of changes of channels. union(left*) \\ union(right*)"""
    left_set, right_set = fill_channel_sets(left, right)
    result = left_set - right_set
    for item in result:
        print(item)


@main.command()
@click.option(
    "--left", "-l", multiple=True, help="Left channel, multiple options allowed"
)
@click.option(
    "--right", "-r", multiple=True, help="Right channel, multiple options allowed"
)
def set_intersection(left, right):
    """Intersection between two sets of changes of channels. union(left*) \\ union(right*)"""
    left_set, right_set = fill_channel_sets(left, right)
    result = left_set & right_set
    for item in result:
        print(item)


@main.command()
@click.option(
    "--channel", "-c", multiple=True, help="Channel, multiple options allowed"
)
def set_union(channel):
    """Union changes of channels. union(channel*)"""
    channel_set = set()
    for item in channel:
        channel_set.update(get_changes(item))
    for item in channel_set:
        print(item)


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
@click.option("--name", "-n", default=None, help="Alias for the new changeset")
def shallow(name):
    """create a new pijul repository from the current revision without history"""
    workdir = Path(".").absolute()
    check_git()
    check_init()
    with TemporaryDirectory() as tmp_dir:
        prepare_workdir(workdir, tmp_dir)
        head, _ = get_head()
        add_recursive()
        new(head)
        record_simple(head, f"commit {head}")
        if name:
            alias(head, name)
            final_message(name)
        else:
            final_message(f"in_{head}")


@main.command()
@click.option(
    "--base", "-b", default=None, help="Update from (commit-ish, default '--root')"
)
@click.option("--head", "-h", default=None, help="Update to (commit-ish, default HEAD)")
@click.option("--name", "-n", default=None, help="Alias for the new changeset")
def update(head, base, name):
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
        fork(base, head)
        run_it(head, base, name)


@main.command()
@click.option("--head", "-h", default=None, help="Import to (commit-ish, default HEAD)")
@click.option(
    "--base", "-b", default=None, help="Import from (commit-ish, default '--root')"
)
@click.option("--name", "-n", default=None, help="Alias for the new changeset")
def create(head, base, name):
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
        new(head)
        run_it(head, base, name)


if __name__ == "__main__":
    main()
