#!/usr/bin/env python3
# Compatibility shim replacing the two private BrainTech packages
# (braintech-utils, braintech-obci-signal-processing) with the minimal
# subset the Perun32 -> LSL streaming path actually needs.

from setuptools import setup, find_namespace_packages

setup(
    name="braintech-compat-shim",
    version="0.1.0",
    description="Minimal stand-ins for private BrainTech deps "
    "(SamplePacket, Impedance, singleton_app)",
    packages=find_namespace_packages(include=["braintech.*"]),
    install_requires=["numpy"],
    python_requires=">=3.6",
)
