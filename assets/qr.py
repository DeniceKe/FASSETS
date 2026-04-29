import io
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

ALPHANUMERIC_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
QR_SIZE = 21
DATA_CODEWORDS = 19
ECC_CODEWORDS = 7


def normalize_tracking_code(raw_code):
    code = str(raw_code or "").strip()
    if not code:
        return ""

    parsed = urlparse(code)
    if parsed.scheme and parsed.netloc:
        query_code = parse_qs(parsed.query).get("code", [""])[0]
        if query_code:
            return normalize_tracking_code(query_code)
        path_bits = [bit for bit in parsed.path.split("/") if bit]
        if path_bits:
            return normalize_tracking_code(path_bits[-1])

    upper_code = code.upper()
    for prefix in ("ASSET:", "FASSETS:", "QR:"):
        if upper_code.startswith(prefix):
            return normalize_tracking_code(code[len(prefix):])

    return code.strip().strip("/")


def make_qr_png(data, *, box_size=8, border=4):
    matrix = make_qr_matrix(data)
    image_size = (QR_SIZE + (border * 2)) * box_size
    image = Image.new("RGB", (image_size, image_size), "white")
    draw = ImageDraw.Draw(image)

    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if not value:
                continue
            x0 = (x + border) * box_size
            y0 = (y + border) * box_size
            draw.rectangle((x0, y0, x0 + box_size - 1, y0 + box_size - 1), fill="black")

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def make_qr_matrix(data):
    normalized = str(data or "").strip().upper()
    if not normalized:
        raise ValueError("QR data cannot be empty.")
    if len(normalized) > 25:
        raise ValueError("Version 1 QR labels support up to 25 characters.")
    if any(char not in ALPHANUMERIC_CHARSET for char in normalized):
        raise ValueError("Only QR-safe alphanumeric asset codes are supported.")

    data_codewords = _build_data_codewords(normalized)
    ecc_codewords = _reed_solomon_remainder(data_codewords, ECC_CODEWORDS)
    all_codewords = data_codewords + ecc_codewords

    modules = [[False] * QR_SIZE for _ in range(QR_SIZE)]
    is_function = [[False] * QR_SIZE for _ in range(QR_SIZE)]

    _draw_finder(modules, is_function, 0, 0)
    _draw_finder(modules, is_function, QR_SIZE - 7, 0)
    _draw_finder(modules, is_function, 0, QR_SIZE - 7)
    _draw_timing_patterns(modules, is_function)
    _set_function_module(modules, is_function, 8, QR_SIZE - 8, True)
    _reserve_format_areas(modules, is_function)
    _draw_data(modules, is_function, all_codewords)
    _draw_format_bits(modules, is_function, error_correction_level_bits=1, mask_pattern=0)
    return modules


def _build_data_codewords(data):
    bits = ["0010", format(len(data), "09b")]

    pairs = [data[index:index + 2] for index in range(0, len(data), 2)]
    for pair in pairs:
        if len(pair) == 2:
            value = ALPHANUMERIC_CHARSET.index(pair[0]) * 45 + ALPHANUMERIC_CHARSET.index(pair[1])
            bits.append(format(value, "011b"))
        else:
            value = ALPHANUMERIC_CHARSET.index(pair)
            bits.append(format(value, "06b"))

    bit_string = "".join(bits)
    capacity = DATA_CODEWORDS * 8
    bit_string += "0" * min(4, capacity - len(bit_string))
    while len(bit_string) % 8 != 0:
        bit_string += "0"

    codewords = [int(bit_string[index:index + 8], 2) for index in range(0, len(bit_string), 8)]
    pad_bytes = [0xEC, 0x11]
    pad_index = 0
    while len(codewords) < DATA_CODEWORDS:
        codewords.append(pad_bytes[pad_index % 2])
        pad_index += 1
    return codewords


def _draw_finder(modules, is_function, left, top):
    for dy in range(-1, 8):
        for dx in range(-1, 8):
            x = left + dx
            y = top + dy
            if not (0 <= x < QR_SIZE and 0 <= y < QR_SIZE):
                continue

            if 0 <= dx <= 6 and 0 <= dy <= 6 and (
                dx in {0, 6}
                or dy in {0, 6}
                or (2 <= dx <= 4 and 2 <= dy <= 4)
            ):
                color = True
            else:
                color = False

            _set_function_module(modules, is_function, x, y, color)


def _draw_timing_patterns(modules, is_function):
    for index in range(8, QR_SIZE - 8):
        value = index % 2 == 0
        _set_function_module(modules, is_function, 6, index, value)
        _set_function_module(modules, is_function, index, 6, value)


def _reserve_format_areas(modules, is_function):
    for index in range(0, 9):
        if index != 6:
            _set_function_module(modules, is_function, 8, index, False)
            _set_function_module(modules, is_function, index, 8, False)
    for index in range(8):
        _set_function_module(modules, is_function, QR_SIZE - 1 - index, 8, False)
        if index < 7:
            _set_function_module(modules, is_function, 8, QR_SIZE - 1 - index, False)


def _draw_data(modules, is_function, codewords):
    bits = []
    for codeword in codewords:
        bits.extend(((codeword >> shift) & 1) for shift in range(7, -1, -1))

    bit_index = 0
    right = QR_SIZE - 1
    while right >= 1:
        if right == 6:
            right -= 1
        upward = ((right + 1) & 2) == 0

        for step in range(QR_SIZE):
            y = QR_SIZE - 1 - step if upward else step
            for offset in range(2):
                x = right - offset
                if is_function[y][x]:
                    continue
                bit = bits[bit_index] if bit_index < len(bits) else 0
                if (x + y) % 2 == 0:
                    bit ^= 1
                modules[y][x] = bool(bit)
                bit_index += 1
        right -= 2


def _draw_format_bits(modules, is_function, *, error_correction_level_bits, mask_pattern):
    format_data = (error_correction_level_bits << 3) | mask_pattern
    format_bits = _append_bch_bits(format_data, 0x537, 10) ^ 0x5412

    for bit_index in range(0, 6):
        _set_function_module(modules, is_function, 8, bit_index, _get_bit(format_bits, bit_index))
    _set_function_module(modules, is_function, 8, 7, _get_bit(format_bits, 6))
    _set_function_module(modules, is_function, 8, 8, _get_bit(format_bits, 7))
    _set_function_module(modules, is_function, 7, 8, _get_bit(format_bits, 8))
    for bit_index in range(9, 15):
        _set_function_module(modules, is_function, 14 - bit_index, 8, _get_bit(format_bits, bit_index))

    for bit_index in range(0, 8):
        _set_function_module(modules, is_function, QR_SIZE - 1 - bit_index, 8, _get_bit(format_bits, bit_index))
    for bit_index in range(8, 15):
        _set_function_module(modules, is_function, 8, QR_SIZE - 15 + bit_index, _get_bit(format_bits, bit_index))


def _reed_solomon_remainder(data, degree):
    generator = _reed_solomon_generator(degree)
    result = [0] * degree
    for value in data:
        factor = value ^ result[0]
        result = result[1:] + [0]
        for index, coefficient in enumerate(generator):
            result[index] ^= _gf_multiply(coefficient, factor)
    return result


def _reed_solomon_generator(degree):
    result = [1]
    for power in range(degree):
        result = _poly_multiply(result, [1, _gf_pow(2, power)])
    return result[1:]


def _poly_multiply(first, second):
    result = [0] * (len(first) + len(second) - 1)
    for first_index, first_value in enumerate(first):
        for second_index, second_value in enumerate(second):
            result[first_index + second_index] ^= _gf_multiply(first_value, second_value)
    return result


def _gf_pow(value, exponent):
    result = 1
    for _ in range(exponent):
        result = _gf_multiply(result, value)
    return result


def _gf_multiply(first, second):
    result = 0
    while second:
        if second & 1:
            result ^= first
        first <<= 1
        if first & 0x100:
            first ^= 0x11D
        second >>= 1
    return result


def _append_bch_bits(value, polynomial, bit_count):
    result = value << bit_count
    while result.bit_length() - polynomial.bit_length() >= 0:
        shift = result.bit_length() - polynomial.bit_length()
        result ^= polynomial << shift
    return (value << bit_count) | result


def _get_bit(value, bit_index):
    return ((value >> bit_index) & 1) != 0


def _set_function_module(modules, is_function, x, y, value):
    modules[y][x] = bool(value)
    is_function[y][x] = True
