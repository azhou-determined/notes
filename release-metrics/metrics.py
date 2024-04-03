import contextlib
import pathlib
from datetime import datetime
import json
import logging
import os
import re
import subprocess
import typing

from matplotlib import pyplot as plot
import numpy as np
from scipy import stats


# Outliers: these tags didn't follow the release process for one reason or another.
# More investigation is needed to include these, exclude them for now.
EXCLUDED_TAGS = ["0.14.1", "0.16.2", "0.27.0"]
SINCE_YEAR = 2022

# Directory to save generated charts
OUTPUT_DIR = "charts"

# Determined repo path
DET_ROOT = "/Users/anda/determined"

# Used to match commit SHAs. Depending on git configuration, this could be 8 or 10 alphanumeric
# characters. It's 8 on my machine.
GIT_COMMIT_SHA_LENGTH = 8


def get_release_tags() -> typing.Dict:
    """
    Get all release + release candidate tags (version + rc).

    Note: some very old releases are omitted because they don't follow this format, and they're very old.
    """
    with pushd(DET_ROOT):
        output = subprocess.run(["git", "tag"], capture_output=True, text=True)
    all_tags = output.stdout.splitlines()

    # Match #.#.#...rc, some older tags don't have a "-" between version and rc
    rc = re.compile(r"^0\.[0-9]+\.[0-9]+[\-]*rc")

    # Match 0.#.#
    r = re.compile(r"^0\.[0-9]+\.[0-9]+$")
    release_tags = list(filter(r.match, all_tags))

    rc_tags = list(filter(rc.match, all_tags))

    # Filter out EE tags.
    rc_tags = list(filter(lambda x: "ee" not in x, rc_tags))

    # Version regex
    r_version = re.compile(r"^0\.[0-9]+\.[0-9]+")

    rc_mapping = {}
    for tag in rc_tags:
        version = r_version.match(tag).group()
        if version not in release_tags:
            continue
        if version not in rc_mapping:
            rc_mapping[version] = []
        rc_mapping[version].append(tag)

    # Filter out versions with only 1 rc.
    rc_mapping = dict(filter(lambda item: len(item[1]) > 1, rc_mapping.items()))

    # Filter out outliers/bad data.
    rc_mapping = dict(
        filter(lambda item: item[0] not in (EXCLUDED_TAGS), rc_mapping.items())
    )

    # Only include newer (> 2022)
    rc_mapping = dict(
        filter(
            lambda item: get_date_for_tag(item[0]).year >= SINCE_YEAR,
            rc_mapping.items(),
        )
    )

    return rc_mapping


def get_release_commits():
    """
    Get a mapping of version -> commit (hash and name) -> [files]
    """
    release_tags = get_release_tags()

    release_commits = {}

    r_commit = re.compile(r"^([a-f0-9]{8}).*")
    commit = None

    # Compare first and last rc's.
    for v, rc in release_tags.items():
        release_commits[v] = {}
        # Get commit name and files in commit.
        log_cmd = ["git", "log", f"{rc[0]}...{rc[-1]}", "--oneline", "--name-only"]
        with pushd(DET_ROOT):
            log_output = subprocess.run(log_cmd, capture_output=True, text=True)

        for line in log_output.stdout.splitlines():
            commit_line = r_commit.match(line)
            if commit_line:
                commit = commit_line.group()
                if commit not in release_commits:
                    release_commits[v][commit] = []
            else:
                # Filepath
                release_commits[v][commit].append(line)

    # Exclude bump version commits.
    for v, commits in release_commits.items():
        commits = dict(
            filter(lambda x: "chore: bump version" not in x[0], commits.items())
        )
        release_commits[v] = commits

    return release_commits


def files_changed():
    release_commits = get_release_commits()

    # Generate a mapping of version -> directory -> number files changed
    release_files = {}
    for v, commits in release_commits.items():
        release_files[v] = {}
        for c, files in commits.items():
            for f in files:
                # Get top-level directory
                top_dir = f.split("/")[0]
                if top_dir not in release_files[v]:
                    release_files[v][top_dir] = 0
                release_files[v][top_dir] += 1

    # Total aggregate files changed per directory across all versions
    total_files = {}
    for v, files in release_files.items():
        for dir_name, count in files.items():
            if dir_name not in total_files:
                total_files[dir_name] = 0
            total_files[dir_name] += count

    # Sort by descending frequency.
    total_files = dict(
        sorted(total_files.items(), key=lambda item: item[1], reverse=True)
    )

    # Filter out outliers.
    total_files = dict(filter(lambda item: item[1] > 1, total_files.items()))
    print(json.dumps(total_files))

    plot_total_directories_pie(total_files)

    all_dirs = list(total_files.keys())
    plot_directories_by_release_bars(release_files, all_dirs)


def plot_directories_by_release_bars(
    files_by_dir_and_release: typing.Dict, dir_names: typing.List
) -> None:
    """
    Plot stacked bar chart of releases and files changed
    """
    all_releases = list(files_by_dir_and_release.keys())
    dirs_releases = {}
    for d in dir_names:
        dirs_releases[d] = [
            files.get(d, 0) for _, files in files_by_dir_and_release.items()
        ]
    plot.figure(figsize=(20, 12))
    # Plot first bar.
    plot.bar(all_releases, dirs_releases[dir_names[0]])
    # Plot remaining dirs.
    bottom = np.array(dirs_releases[dir_names[0]])
    for i in range(1, len(dir_names)):
        plot.bar(all_releases, dirs_releases[dir_names[i]], bottom=bottom)
        bottom += np.array(dirs_releases[dir_names[i]])

    plot.xlabel("Version")
    plot.ylabel("Files Changed")
    plot.legend(dir_names)
    plot.title("Files changed per release")
    plot.xticks(rotation=45, ha="right")
    plot.savefig(f"{OUTPUT_DIR}/files-changed-per-release-since-{SINCE_YEAR}")


def plot_total_directories_pie(files_by_dir: typing.Dict) -> None:
    """
    Plot piechart of total files by directory.
    """
    fig, ax = plot.subplots()
    ax.pie(files_by_dir.values(), labels=files_by_dir.keys(), autopct="%1.1f%%")
    plot.title("Files changed across all releases")
    plot.savefig(f"{OUTPUT_DIR}/all-files-changed-since-{SINCE_YEAR}-pie")


def get_date_for_tag(rc_tag: str):
    """
    Get the date from the first commit for an `-rc` tag.
    """
    cmd = [
        "git",
        "log",
        "-1",
        rc_tag,
        "--oneline",
        "--date=short",
        "--pretty=format:%h,%ad,%s",
    ]
    with pushd(DET_ROOT):
        output = subprocess.run(cmd, capture_output=True, text=True)
    for line in output.stdout.splitlines():
        split_line = line.split(",")
        date = split_line[1]
        return datetime.strptime(date, "%Y-%m-%d").date()


def time_to_release():
    """
    Compares days between rc0 and final version tag
    """
    release_days = {}
    all_release_tags = get_release_tags()
    for v, rcs in all_release_tags.items():
        v_date = get_date_for_tag(v)
        # v_date = datetime.strptime(v_date_str, "%Y-%m-%d").date()
        first_rc = rcs[0]
        first_rc_date = get_date_for_tag(first_rc)
        # first_rc_date = datetime.strptime(first_rc_date_str, "%Y-%m-%d").date()
        delta_busdays = np.busday_count(first_rc_date, v_date)
        release_days[v] = {"release_date": v_date, "delta": delta_busdays}

    # Filter by date.
    release_days = dict(
        filter(
            lambda item: item[1]["release_date"].year >= SINCE_YEAR,
            release_days.items(),
        )
    )

    # Sort by release date.
    release_days = dict(
        sorted(release_days.items(), key=lambda item: item[1]["release_date"])
    )

    # Get just delta.
    for v, d in release_days.items():
        release_days[v] = d["delta"]

    plot_release_days_bar(release_days)

    plot_release_days_by_commits_scatter(release_days)


def plot_release_days_bar(release_days: typing.Dict) -> None:
    plot.figure(figsize=(20, 10))
    plot.bar(x=release_days.keys(), height=release_days.values())
    plot.xlabel("Version")
    plot.ylabel("Days to Release")
    plot.title("Days to Release by Version")
    plot.xticks(rotation=45, ha="right")
    plot.savefig(f"{OUTPUT_DIR}/days-to-release-since-{SINCE_YEAR}")


def plot_release_days_by_commits_scatter(release_days: typing.Dict) -> None:
    release_commits = get_release_commits()

    # Count number of commits per release.
    for v, commits in release_commits.items():
        release_commits[v] = len(commits.items())
    # assert len(release_days.items()) == len(release_commits.items())

    num_days = list(release_days.values())
    # Base release_commits off release_days since the latter is sorted.
    num_commits = [release_commits[v] for v in release_days.keys()]

    fig, ax = plot.subplots(1, figsize=(15, 10))
    ax.scatter(num_days, num_commits)

    # Keep track of annotations to avoid overlapping text.
    annotations = []
    for i, v in enumerate(release_days.keys()):
        point = (num_days[i], num_commits[i])
        if point in annotations:
            # Hacky way to avoid overlap.
            v = f"{' ' * 10}, {v}"
        ax.annotate(v, point)
        annotations.append(point)
    r, p = stats.pearsonr(num_days, num_commits)

    ax.annotate(f"r = {r:.2f}", xy=(1, 1), color="blue", xycoords="axes fraction")
    plot.xlabel("Days to Release")
    plot.ylabel("Number of Commits Since rc0")
    plot.title("Days to Release by Fixes Merged")
    plot.savefig(f"{OUTPUT_DIR}/days-to-release-by-fixes-since-{SINCE_YEAR}")


@contextlib.contextmanager
def pushd(x):
    """
    Enter a new working directory and exit when the context exits.
    """
    cwd = os.getcwd()
    os.chdir(x)
    try:
        yield
    finally:
        os.chdir(cwd)


def init():
    with pushd(DET_ROOT):
        logging.info(f"Fetching tags")
        subprocess.run(["git", "fetch", "--tags"])

    pathlib.Path(OUTPUT_DIR).mkdir(exist_ok=True)


if __name__ == "__main__":
    init()
    files_changed()
    time_to_release()
