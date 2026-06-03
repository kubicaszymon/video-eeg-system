# Tests for BCI-Framework

## How to run
Execute commands below from repository root (obci).
To install dependencies:

```
pip3 install --user -e .[test]
```

You can run whole test suite using setup.py or pytest directly:

```
pytest
```

### Useful commands

To disable output capturing (useful for investigating logs or running a debugger), use:

```
pytest -s
```

To run a specific test file, class or function, use `pytest -k <name of class/file/function/>`.
This will execute all tests matching given pattern. For example:

```
pytest -k test_message_receiving
```

## Structure of test dirs

    + test
    | + control
    | + core
    | | + messages
    | + drivers
    | | + video
    | | + data
    | + logs
    | + peers
    | | + data
    | + signal_processing
    | | + data
    | + utils

## How it works
- Test folders can have their own `conftest.py` with fixtures and helpers, aside from `conftest.py` in test root.
- Test data is placed in `data` dir beside test file that uses it. If more tests from different dirs share
  the same data, the files should be symlinked.
- Subfolders corresponding to obci sub-subpackages (eg. test/core/messages/) should be created when there are
  at least 3-4 test files that would fall in.
- Fixtures and helpers that can be useful for writing tests in external obci modules should be placed in `obci/test`.
- When integration tests are added, existing hierarchy should be moved to a parent dir, eg. `test/unit/`.

## Requirements
- All tests which create peers should ensure proper teardown in case of error to free up system resources
  (preferably through the use of pytest fixtures).
