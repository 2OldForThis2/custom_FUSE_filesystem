#!/bin/bash
cd ~/Desktop/fuse_project
source venv/bin/activate
export FUSE_LIBRARY_PATH=/lib/x86_64-linux-gnu/libfuse.so.2
python3 custom_fuse.py
