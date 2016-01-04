# std lib
import errno
import fcntl
import hashlib
import os
import shutil

__all__ = ['DATA_DIR']

# a mapping of the names for checksum methods.
supported_checksum_methods = {
    'md5': hashlib.md5,
    'sha1': hashlib.sha1,
    'sha256': hashlib.sha256,
}

# you really should override this.
DATA_DIR = os.getenv("NAPFS_DATA_DIR", "/tmp/napfs")

# path to data.
PATH_TPL = DATA_DIR + "%s"


def _mkdirs(dir_name):
    # there's a race condition where we could see the directory doesn't exist
    # and then hit an error when trying to create the directory because
    # another process is doing the same thing at the exact same time.
    # if that's the case, swallow the error.
    if os.path.exists(dir_name):
        return
    try:
        os.makedirs(dir_name)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def copy_file(src, dst):
    local_src = PATH_TPL % src
    local_dst = PATH_TPL % dst
    _mkdirs(os.path.dirname(local_dst))
    shutil.copy(local_src, local_dst)


def delete_file(path):
    local_path = PATH_TPL % path
    try:
        os.unlink(local_path)
    except (IOError, OSError):
        pass

    return False if os.path.exists(local_path) else True


def open_file(path, mode='rb'):
    return open(PATH_TPL % path, mode=mode)


def _initialize_file_path(path):
    """
    :param path:
    :return:
    """
    if os.path.exists(path):
        return

    _mkdirs(os.path.dirname(path))

    # touch the file to make sure it exists
    open(path, 'ab').close()


def write_file_chunk(path, stream, offset, chunk_size):

    local_path = PATH_TPL % path
    _initialize_file_path(local_path)

    with open(local_path, 'rb+') as f:
        if chunk_size:
            fcntl.lockf(f, fcntl.LOCK_EX, chunk_size, offset, 0)
        else:
            fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(offset)
        f.write(stream.read())
        return f.tell()


def read_file_chunk(f, first_byte, length):
    """
    utility generator function to serve up the bytes
    allows us to return the response headers and then stream the bytes
    to the client without blocking or buffering all the bytes into memory.

    this is especially important for really big files.

    :param local_path:
    :param first_byte:
    :param last_byte:
    :return:
    """
    def response():

        with f:
            f.seek(first_byte)
            bytes_left = length
            while bytes_left > 0:
                chunk_size = min(bytes_left, 1024)
                data = f.read(chunk_size)
                bytes_left -= chunk_size
                yield data

    return response


def checksum_response(response, checksum):
    hashcalc = supported_checksum_methods.get(checksum, hashlib.sha1)()
    for chunk in response():
        hashcalc.update(chunk)
    return hashcalc.hexdigest()
