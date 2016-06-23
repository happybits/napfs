import re

BYTE_RANGE_STRING_PATTERN = re.compile(r'^([0-9]+)\-([0-9]+)$')
_BYTE_RANGE_HEADER_PATTERN = re.compile(r'^bytes=([0-9]+)\-([0-9]+)?$')


def parse_byte_range_header(range_header):
    """
    when the client/browser sends a byte range request header, parse it into
    min/max ints. If the client sends a header in the form of:

      Range: bytes=100-

    with no second param, use an empty string to indicate the wild-card max
    value.

    If we can't parse the header, assume they want the whole file.
    Maybe we should throw an error if it is not the right form?
    And only assume all content if the client sends no range header at all?

    :param range_header: str
    :return: int, int
    """
    try:
        m = re.match(_BYTE_RANGE_HEADER_PATTERN, range_header)
        first_byte = int(m.group(1))
        last_byte = '' if m.group(2) is None else int(m.group(2))
    except(AttributeError, TypeError):
        first_byte = 0
        last_byte = ''
    return first_byte, last_byte


def parse_byte_ranges_from_list(parts):
    """
    Take a list of byte range strings and turn them into a list of min, max
    ints sorted in ascending order. This comes from querying a sorted set in
    redis for all the previously uploaded bytes.
    :param parts:
    :return: list
    """
    ranges = []
    for byte_range_string in parts:
        try:
            m = re.match(BYTE_RANGE_STRING_PATTERN, byte_range_string)
            byte_range = int(m.group(1)), int(m.group(2))
            ranges.append(byte_range)
        except (AttributeError, TypeError):
            continue
    return sorted(ranges)


def get_max_from_contiguous_byte_ranges(parts):
    """
    given a parsed list of min/max byte ranges in ascending order,
    figure out what is the max contiguous byte range uploaded so far.
    We use this to determine what part of the upload we can stream back to the
    client. Since there's no guarantee what order the uploader will send the
    chunks of the video file, we have to be careful to only serve up the part
    of the video file that is readable so far.
    :param parts: list
    :return: int
    """
    sorted_parts = sorted(parts)

    # If the part list doesn't start with 0, there is no content available
    try:
        if sorted_parts[0][0] != 0:
            return 0
    except IndexError:
        return 0

    mp = None
    # pylint: disable=unsubscriptable-object
    for p in sorted_parts:
        if mp is None or (p[0] - 1 <= mp[1] and p[1] >= mp[1]):
            mp = p
    return 0 if mp is None else mp[1]


def condense_byte_ranges(byte_ranges):
    """
    any overlapping byte-ranges can be consolidated into a single range.
    This makes the ranges simpler and more compact.

    :param byte_ranges:
    :return: list
    """
    byte_ranges = sorted(byte_ranges)
    new_byte_ranges = []
    i = 0
    byte_range_len = len(byte_ranges)
    while i < byte_range_len:
        x = byte_ranges[i]
        try:
            y = byte_ranges[i + 1]
        except IndexError:
            new_byte_ranges.append(x)
            break

        if y[0] > x[1] + 1:
            new_byte_ranges.append(x)

        else:
            byte_ranges[i + 1] = [x[0], y[1]]
        i += 1
    return new_byte_ranges
