# set up environment before run

cd ~/Desktop/fuse_project

sudo apt install python3-venv python3-full libfuse2

python3 -m venv venv

source venv/bin/activate

python3 -m pip install fusepy

chmod +x run_fuse.sh

./run_fuse.sh
