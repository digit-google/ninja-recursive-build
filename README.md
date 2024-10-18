# A minimal super-build used to verify Ninja's jobserver implementation.

This repository contains a top-level Ninja `build.ninja` plan which recursively
invokes several Ninja plans corresponding to various open-source projects
found under the `projects/` directory, provided as Git sub-modules.

It is used to verify the correctness of Ninja jobserver implementations.
For context, see https://github.com/ninja-build/ninja/issues/1139

## Requirements

Clone this repository with `--recurse-submodules`. If you forgot about it,
go into your cloned repository, then run `git submodule update --init --recursive`.

You must have a valid C++ compiler, a `ninja` tool and `python3` in your path.

Note that it is possible to use a custom Ninja binary by re-generating
the top-level build plan with `tools/generate_plan.py --ninja=$NINJA > build.ninja`.

## Setup

Run `tools/generate_plan.py > build.ninja` to generate a top-level Ninja build
plan from the content of your `projects/` directory (see below for details).

Run `ninja configure` once to ensure that all project sub-builds are configured
properly.

## Usage

Run `ninja clean` to clean all previously built artifacts in all sub-projects.

Run `ninja` or `ninja build-all` to build everything. Use extra arguments as
you would with Ninja, e.g. `ninja -j8` or `ninja --jobserver` if your version
supports it.

Run `tools/jobserver_pool.py ninja <args...>` to setup a jobserver pool and run
Ninja under it. By default, the pool uses the same number of jobs as your
CPU core count.

Run `tools/jobserver_pool.py -jCOUNT ninja <args...>` to setup
a jobserver pool with `COUNT` jobs instead, and run Ninja under it.

Run `ninja generate-trace` to generate a `build_trace.json` file that describes
how build tasks were scheduled during the last build. **NOTE**: This information is
only correct if you performed a clean build (e.g. `ninja clean && ninja`).

This trace file follows the Chrome tracing format, so can be uploaded to
https://ui.perfetto.dev, to https://profiler.firefox.com or in the
`about:tracing` tab of any Chromium-based browser.

Detailed comparison performances can be performed with the
[`hyperfine`](https://github.com/sharkdp/hyperfine) tool
using something like:

```
hyperfine --prepare "ninja clean" \
          "ninja -j8" \
          "tools/jobserver_pool.py -j8 ninja"
```

## Using a custom `ninja` binary

The default build plan assumes that the `ninja` program found in your `PATH` will
be used to invoke the sub-builds. It is possible to use a different binary by
re-generating the build plan with a command such as:

```
tools/generate_plan.py --ninja=$NINJA > build.ninja
```

Where `$NINJA` points to your custom `ninja` binary. You do not need to re-run
the `ninja configure` step everytime you do that.

Warning: You still need to invoke the top-level build-plan with `$NINJA`, not `ninja`,
as this only affects the version used to invoke the sub-builds.

## Adding more projects

It is possible to add more projects (i.e. sub-builds), if they do support CMake,
by simply adding submodules under the `projects/` directory, then re-generating the
build plan, and re-configuring.

```
# Add a new project for freetype. Checkout a specific version for
# more reproducible results.
git submodule add https://gitlab.freedesktop.org/freetype/freetype.git projects/freetype
git -C projects/freetype checkout VER-2-13-3

# Regenerate the top-level build plan
tools/generate_plan.py > build.ninja

# Reconfigure everything
ninja configure
```

The build plan generation script looks under `projects/*/CMakeLists.txt` and
`projects/*/build/cmake/CMakeLists.txt` and only adds sub-builds for matching
files, and ignores the rest.

## Important considerations when benchmarking

### Python startup time latency

When using the `tools/jobserver_pool.py` script to act as a jobserver pool, be
aware that starting a Python script directly can have noticeable latency during
benchmarking. This can reduced by invoking the python interpreter directly with
the `-S` flag to disallow searching for locally-installed modules, e.g.:

```
python3 -S tools/jobserver_py -j<COUNT> ...
```

Depending on your system's configuration, and your curren Python environment,
this can save several hundred milliseconds from each start.

A version of `ninja` which implements the jobserver pool directly (as with
a `--jobserver` option) is preferred due to this issue.


### Ensure the jobserver pool size is equal or larger than the number of available CPU cores

While a command like `ninja -j<COUNT>` limits Ninja to dispatch at most `COUNT`
tasks in parallel, this does not prevent said tasks to create more threads (and
thus using more CPU cores when more are available on the system). For example, on
a 16-core machine, a command like:

```
/usr/bin/time --format="%Eelapsed %PCPU" ninja -j8
```

Will print something like `0:14.50elapsed 1176%CPU`, showing that more than
8 CPU cores were used (due to the %CPU value being higher than 800).

When using a jobserver server with 8 tokens though, participating tasks use
the shared pool instead, and will strictly not use more than 8 CPUs. This makes
the build _slower_ in comparison. In other words, something like:

```
/usr/bin/time --format=%PCPU tools/jobserver_pool.py -j8 ninja
```

Will print something like `0:25.92elapsed 618%CPU` instead, showing that the build
is about twice longer since it didn't use more than 8 CPUs (since 618 < 800).

When benchmarking whether a jobserver pool improves things for you, always
ensure that the parallelism count passed to Ninja matches your available CPU core
count, or the results will not be correctly comparable.

On Linux, it is possible to create a shell session that only uses a fixed amount
of CPUs, with a command like:

```
# Start a shell with a restricted CPU set (only 8 cpus allowed).
systemd-run --scope --property AllowedCPUs=0-7 bash -i
```

Or this can be used to invoke `hyperfine` directly, e.g.:
```
systemd-run --scope --property AllowedCPUs=0-7 hyperfine ....
```

NOTE: `systemd-run` will prompt the user for elevated privileges. If you are using
`ssh` and cannot access a graphical desktop to accept it, you may need to use
`sudo` twice instead, as in:

```
# Start a shell with a restrict CPU set, using `sudo` to escalate privileges to root
# then switching back to the current user.
sudo systemd-run --scope --property AllowedCPUs=0-7 sudo -u $USER bash -i
```

