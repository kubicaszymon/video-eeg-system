
To install Python module use:

```
pip3 install --user -e .
```

To Python module build use:

```
python3 setup.py build_ext --inplace
```

C++ code inside `src` directory depends only on C++11 standard library.

Tests inside `tests` directory require Boost libraries.

To build tests run `cmake . && make -j4` inside this directory.

TMSI kernel driver is available from https://gitlab.com/braintech/tmsi-dkms.git.

To reformat C++ code run:

`astyle --style=allman -s4 -S -p -U -k2 -c -M120 ./src/*.cpp ./src/*.h ./src/tmsi/*.cpp ./src/tmsi/*.c ./src/tmsi/*.h ./tests/*.cpp ./tests/*.h`

