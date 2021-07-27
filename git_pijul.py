import sys
from datetime import datetime
from os import environ
from pathlib import Path
from subprocess import PIPE, CalledProcessError, run

from tqdm import tqdm

# TODO
#
# * Make it a package: pijul-tools
# * Add click
# * Add toml to temporarily set name, full_name, email
# * Add --continue to skip the base and make it easier to continue
# * Call it pijul-git

batch = dict(environ)
batch["VISUAL"] = "/bin/true"
track_count = "-l10000"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def clean():
    run(["git", "clean", "-xdfq", "-e", ".pijul"], check=True)


def git_reset():
    run(["git", "reset"], check=True)


def restore():
    run(["git", "checkout", "--no-overlay", "-q", "."], check=True)


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


def get_base():
    return (
        run(["git", "rev-list", "--all"], check=True, stdout=PIPE)
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
    for line in log.splitlines():
        found = False
        for tag in ("Date", "Author"):
            if get_tag(res, tag, line):
                found = True
        if not found:
            out.append(line.strip())
    return "\n".join(out), res["author"], parse_date(res["date"])


def rev_list(branch, base):
    return (
        run(
            [
                "git",
                "rev-list",
                "--topo-order",
                "--ancestry-path",
                "--no-merges",
                f"{base}..{branch}",
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


def force_reset():
    git_reset()
    clean()
    restore()


def get_args():
    arg_len = len(sys.argv)
    branch = None
    base = None
    if arg_len > 1:
        branch = sys.argv[1]
    if arg_len > 2:
        base = sys.argv[2]
    if not branch:
        branch = "origin/master"
    if not base:
        base = get_base()
    return branch, base


class Runner:
    def __init__(self, revs):
        self.revs = revs
        self.here = Path(".").absolute()

    def run(self):
        prev = self.revs.pop()
        rev = self.revs.pop()
        checkout(rev)
        add_recursive()
        with tqdm(total=len(self.revs)) as pbar:
            while self.revs:
                if self.step(prev, rev):
                    prev = rev
                    rev = self.revs.pop()
                    pbar.update()
            self.step(prev, rev)
            run(["pijul", "fork", rev], check=True)

    def prepare(self, prev, rev):
        checkout(rev)
        log = show()
        log, author, date = parse_log(log)
        timestamp = str(int(date.timestamp()))
        return log, author, timestamp

    def step(self, prev, rev):
        hash_ = None
        try:
            log, author, timestamp = self.prepare(prev, rev)
            add_recursive()
            out, err = record(log, author, timestamp)
            _, _, hash_ = out.partition("Hash:")
            hash_ = hash_.strip()
        except CalledProcessError as e:
            self.handle_error(rev, hash_, e)
            return False
        return True


def main():
    branch, base = get_args()
    revs = rev_list(branch, base)
    force_reset()
    runner = Runner(revs)
    runner.run()


if __name__ == "__main__":
    main()
