# std lib
import errno
import fcntl
import hashlib
import os
import shutil

__all__ = []

# a mapping of the names for checksum methods.
supported_checksum_methods = {
    'md5': hashlib.md5,
    'sha1': hashlib.sha1,
    'sha256': hashlib.sha256,
}


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
    _mkdirs(os.path.dirname(dst))
    shutil.copy(src, dst)


def delete_file(path):
    try:
        os.unlink(path)
    except (IOError, OSError):
        pass

    return False if os.path.exists(path) else True


def open_file(path, mode='rb'):
    return open(path, mode=mode)


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

    _initialize_file_path(path)

    with open(path, 'rb+') as f:
        if chunk_size:
            fcntl.lockf(f, fcntl.LOCK_EX, chunk_size, offset, 0)
        else:
            fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(offset)
        f.write(stream.read(chunk_size))
        return f.tell()


def read_file_chunk(f, first_byte, length):
    """
    utility generator function to serve up the bytes
    allows us to return the response headers and then stream the bytes
    to the client without blocking or buffering all the bytes into memory.

    this is especially important for really big files.

    :param f:
    :param length:
    :param first_byte:
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
