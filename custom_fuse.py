#!/usr/bin/env python3

import os
import shutil
import errno
import time
from datetime import datetime
from fuse import FUSE, FuseOSError, Operations


STORAGE_DIR = os.path.expanduser("~/Desktop/fuse_project/storage")
BACKUP_DIR = os.path.expanduser("~/Desktop/fuse_project/backup")
EXPIRED_DIR = os.path.expanduser("~/Desktop/fuse_project/expired")
MOUNT_DIR = os.path.expanduser("~/Desktop/fuse_project/mount")

EXPIRE_SECONDS = 90

# create folder if not exist
def make_sure_folders_exist():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(EXPIRED_DIR, exist_ok=True)
    os.makedirs(MOUNT_DIR, exist_ok=True)

# path: /test.txt
# full path: /home/user/Desktop/fuse_project/storage/test.txt
def get_full_path(path):
    if path.startswith("/"):
        path = path[1:]
    return os.path.join(STORAGE_DIR, path)

# change hm/test.txt to hm_test.txt_202604/01_123456.bak
def build_backup_path(path):
    clean_name = path.strip("/").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{clean_name}_{timestamp}.bak"

# convert /hm/test.txt to /home/user/Desktop/fuse_project/backup/hm_test.txt_202604/01_123456.bak
def get_backup_path(path):
    file_name = build_backup_path(path)
    return os.path.join(BACKUP_DIR, file_name)

# shutil.copy(): copy + permission(read/write/execute)
# shutil.copy2() copy + permission + metadata
def save_old_version(full_path, path):
    if os.path.isfile(full_path):
        backup_path = get_backup_path(path)
        shutil.copy2(full_path, backup_path)
        print(f"[BACKUP] {backup_path}")

# check if the file is expired by comparing pass_time with expire_seconds
def file_is_expired(full_path):
    if not os.path.isfile(full_path):
        return False

    current_time = time.time()
    modified_time = os.path.getmtime(full_path) # file last modified time
    pass_time = current_time - modified_time
    return pass_time > EXPIRE_SECONDS 


def build_expired_path(path):
    strip_name = path.strip("/").replace("/", "_")
    # expired_path = "/home/user/Desktop/fuse_project/expired/test.txt"
    expired_path = os.path.join(EXPIRED_DIR, strip_name)

    original_path = expired_path

    # if expired_path already exists, add number at the end to aviod replacement
    count = 1
    while os.path.exists(expired_path):
        expired_path = f"{original_path}_{count}"
        count += 1

    return expired_path

# take source file path and make it exist in expired folder
# if file does not exist yet, it will be created in expired folder.
def move_one_file_to_expired(full_path, path):
    if not os.path.isfile(full_path):
        return

    expired_path = build_expired_path(path)
    shutil.move(full_path, expired_path)
    print(f"[EXPIRED] {expired_path}")

# check all files in /storage
# if any file is expired, move it to /expired
# os.path.relpath(target, start): return how to reach target from start
#   use relative path to isolate file path inside /storage
#   build expired_path and move to /expired
def move_expired_files():
    for root, dirs, files in os.walk(STORAGE_DIR):
        for name in files:
            full_path = os.path.join(root, name)
            relative_path = os.path.relpath(full_path, STORAGE_DIR)
            fuse_path = "/" + relative_path # /test.txt

            if file_is_expired(full_path):
                move_one_file_to_expired(full_path, fuse_path)


class FS(Operations):
    def __init__(self):
        make_sure_folders_exist()
        move_expired_files()
        self.backup_done = set() # set for files that have been backed up

    # backup file if not backed up yet
    def backup_once(self, path, full_path):
        if path not in self.backup_done and os.path.isfile(full_path):
            save_old_version(full_path, path)
            self.backup_done.add(path)

    # will trigger when ls, cat, open... to get attributes
    def getattr(self, path, fh=None):
        move_expired_files()
        full_path = get_full_path(path)

        if not os.path.exists(full_path):
            raise FuseOSError(errno.ENOENT)

        st = os.lstat(full_path)
        return {
            "st_atime": st.st_atime,    # last access time
            "st_ctime": st.st_ctime,    # last metadata change
            "st_gid": st.st_gid,        # group id for permission to read/write
            "st_mode": st.st_mode,      # store file types and permission
            "st_mtime": st.st_mtime,    # last modified time (used in modified_time)
            "st_nlink": st.st_nlink,    # number of hard link
            "st_size": st.st_size,      # file size
            "st_uid": st.st_uid,        # return the owner's user id
        }

    # listing directory
    def readdir(self, path, fh):
        move_expired_files()
        full_path = get_full_path(path)

        entries = [".", ".."]   # current directory and parent directory will always exist
        if os.path.isdir(full_path):
            entries.extend(os.listdir(full_path))   # add all files in the entries

        # yield: return entry one at a time since fuse expect one at a time
        for entry in entries:
            yield entry 

    def open(self, path, flags):
        move_expired_files()
        full_path = get_full_path(path)

        if not os.path.exists(full_path):
            raise FuseOSError(errno.ENOENT)

        # remove backup record if file is opened in case it needs to backup again after modified
        # self.backup_done.discard(path) 

        # writeonly, readwrite, append(every write will append to the end of file)
        if (flags & os.O_WRONLY) or (flags & os.O_RDWR) or (flags & os.O_APPEND):
            self.backup_once(path, full_path)

        return os.open(full_path, flags)

    def create(self, path, mode, fi=None):
        full_path = get_full_path(path)
        parent_dir = os.path.dirname(full_path) # find the folder where the file is located
        os.makedirs(parent_dir, exist_ok=True) # make sure parent folder exist
        # if file exitst, open; if not, create new file and open
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    # move to requested offset and read data from file
    def read(self, path, size, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, size)

    # move to requested offset and write data to file
    def write(self, path, data, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, data)

    # used when rewrite file with new content, clear out old content
    # or keep the file at a certian size
    def truncate(self, path, length, fh=None):
        full_path = get_full_path(path)

        with open(full_path, "r+") as f:     # r+: reading and writing
            f.truncate(length)

    # remove file
    def unlink(self, path):
        full_path = get_full_path(path)
        os.unlink(full_path)

    # create directory
    def mkdir(self, path, mode):
        full_path = get_full_path(path)
        os.makedirs(full_path, mode=mode, exist_ok=False)

    # remove directory, only works if the folder is empty
    def rmdir(self, path):
        full_path = get_full_path(path)
        os.rmdir(full_path)

    # rename folder or move to new directory
    def rename(self, old, new):
        old_path = get_full_path(old)
        new_path = get_full_path(new)

        parent_dir = os.path.dirname(new_path)
        os.makedirs(parent_dir, exist_ok=True)

        os.rename(old_path, new_path)

    # update file access time(last read) and modification time(last content change)
    def utimens(self, path, times=None):
        full_path = get_full_path(path)
        os.utime(full_path, times)

    # close file
    # should not backup more than once for the same session
    def release(self, path, fh):
        self.backup_done.discard(path)
        return os.close(fh)


if __name__ == "__main__":
    make_sure_folders_exist()

    print("Starting FUSE System...")
    print("Mount folder:", MOUNT_DIR)
    print("Storage folder:", STORAGE_DIR)
    print("Backup folder:", BACKUP_DIR)
    print("Expired folder:", EXPIRED_DIR)

    FUSE(FS(), MOUNT_DIR, foreground=True)
