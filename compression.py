import heapq
from collections import defaultdict

########################################
# BWT + MTF + RLE + Huffman (для небольших/текстовых данных)
# и без BWT (для больших/бинарных)
########################################

def bwt_transform(data: bytes) -> (bytes, int):
    s = data.decode('latin1')
    s += '\0'
    rotations = [s[i:] + s[:i] for i in range(len(s))]
    rotations_sorted = sorted(rotations)
    last_column = ''.join(rot[-1] for rot in rotations_sorted)
    original_index = rotations_sorted.index(s)
    return last_column.encode('latin1'), original_index

def inverse_bwt(last_column: bytes, index: int) -> bytes:
    s = list(last_column.decode('latin1'))
    n = len(s)
    table = [""] * n
    for _ in range(n):
        table = sorted([s[i] + table[i] for i in range(n)])
    result = table[index]
    if result[-1] == '\0':
        result = result[:-1]
    return result.encode('latin1')

def mtf_encode(data: list[int]) -> list[int]:
    symbols = list(range(256))
    output = []
    for b in data:
        index = symbols.index(b)
        output.append(index)
        symbols.pop(index)
        symbols.insert(0, b)
    return output

def mtf_decode(data: list[int]) -> list[int]:
    symbols = list(range(256))
    output = []
    for idx in data:
        b = symbols[idx]
        output.append(b)
        symbols.pop(idx)
        symbols.insert(0, b)
    return output

RLE_MARKER = 256

def rle_encode(data: list[int]) -> list[int]:
    output = []
    i = 0
    while i < len(data):
        count = 1
        while i + count < len(data) and data[i] == data[i+count]:
            count += 1
        if count > 3:
            output.append(RLE_MARKER)
            output.append(data[i])
            output.append(count)
        else:
            output.extend(data[i:i+count])
        i += count
    return output

def rle_decode(data: list[int]) -> list[int]:
    output = []
    i = 0
    while i < len(data):
        if data[i] == RLE_MARKER:
            value = data[i+1]
            count = data[i+2]
            output.extend([value] * count)
            i += 3
        else:
            output.append(data[i])
            i += 1
    return output

class HuffmanNode:
    def __init__(self, symbol, freq, left=None, right=None):
        self.symbol = symbol
        self.freq = freq
        self.left = left
        self.right = right
    def __lt__(self, other):
        return self.freq < other.freq

def build_frequency_table(data: list[int]) -> dict:
    freq = defaultdict(int)
    for symbol in data:
        freq[symbol] += 1
    return dict(freq)

def build_huffman_tree(freq: dict) -> HuffmanNode:
    heap = []
    for symbol, frequency in freq.items():
        heapq.heappush(heap, HuffmanNode(symbol, frequency))
    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        merged = HuffmanNode(None, left.freq + right.freq, left, right)
        heapq.heappush(heap, merged)
    return heap[0] if heap else None

def generate_huffman_codes(node, prefix="", codebook=None):
    if codebook is None:
        codebook = {}
    if node is None:
        return codebook
    if node.symbol is not None:
        codebook[node.symbol] = prefix or "0"
    generate_huffman_codes(node.left, prefix + "0", codebook)
    generate_huffman_codes(node.right, prefix + "1", codebook)
    return codebook

def huffman_encode(data: list[int]) -> (str, HuffmanNode):
    freq = build_frequency_table(data)
    tree = build_huffman_tree(freq)
    codebook = generate_huffman_codes(tree)
    encoded = "".join(codebook[symbol] for symbol in data)
    return encoded, tree

def huffman_decode(bitstring: str, tree: HuffmanNode) -> list[int]:
    output = []
    node = tree
    for bit in bitstring:
        node = node.left if bit == '0' else node.right
        if node.left is None and node.right is None:
            output.append(node.symbol)
            node = tree
    return output

def pack_bitstring(bitstring: str) -> bytes:
    padding = (8 - len(bitstring) % 8) % 8
    bitstring += "0" * padding
    result = bytearray()
    for i in range(0, len(bitstring), 8):
        byte = bitstring[i:i+8]
        result.append(int(byte, 2))
    return bytes([padding]) + bytes(result)

def unpack_bitstring(data: bytes) -> str:
    padding = data[0]
    bits = ""
    for byte in data[1:]:
        bits += format(byte, '08b')
    if padding:
        bits = bits[:-padding]
    return bits

def pack_frequency_table(freq: dict) -> bytes:
    result = bytearray()
    # 4 байта для количества записей
    result += len(freq).to_bytes(4, 'little')
    for symbol, f in freq.items():
        result += symbol.to_bytes(2, 'little')
        result += f.to_bytes(4, 'little')
    return bytes(result)

def unpack_frequency_table(data: bytes) -> (dict, int):
    num_items = int.from_bytes(data[0:4], 'little')
    freq = {}
    offset = 4
    for _ in range(num_items):
        symbol = int.from_bytes(data[offset:offset+2], 'little')
        offset += 2
        f = int.from_bytes(data[offset:offset+4], 'little')
        offset += 4
        freq[symbol] = f
    return freq, offset

def build_huffman_tree_from_frequency(freq: dict) -> HuffmanNode:
    return build_huffman_tree(freq)

########################################
# Сжатие для небольших данных (с BWT)
########################################
def compress_small(data: bytes) -> bytes:
    bwt_data, original_index = bwt_transform(data)
    mtf_encoded = mtf_encode(list(bwt_data))
    rle_encoded = rle_encode(mtf_encoded)
    encoded_bits, _ = huffman_encode(rle_encoded)
    freq = build_frequency_table(rle_encoded)
    header = original_index.to_bytes(4, 'little') + pack_frequency_table(freq)
    huffman_bytes = pack_bitstring(encoded_bits)
    return header + huffman_bytes

def decompress_small(data: bytes) -> bytes:
    original_index = int.from_bytes(data[:4], 'little')
    freq, header_length = unpack_frequency_table(data[4:])
    header_total = 4 + header_length
    huffman_encoded_bytes = data[header_total:]
    bitstring = unpack_bitstring(huffman_encoded_bytes)
    huffman_tree = build_huffman_tree_from_frequency(freq)
    rle_decoded = huffman_decode(bitstring, huffman_tree)
    mtf_decoded = rle_decode(rle_decoded)
    bwt_data = bytes(mtf_decode(mtf_decoded))
    return inverse_bwt(bwt_data, original_index)

########################################
# Сжатие для больших/бинарных данных (без BWT)
########################################
def compress_large(data: bytes) -> bytes:
    mtf_encoded = mtf_encode(list(data))
    rle_encoded = rle_encode(mtf_encoded)
    encoded_bits, _ = huffman_encode(rle_encoded)
    freq = build_frequency_table(rle_encoded)
    header = pack_frequency_table(freq)
    huffman_bytes = pack_bitstring(encoded_bits)
    return header + huffman_bytes

def decompress_large(data: bytes) -> bytes:
    freq, header_length = unpack_frequency_table(data)
    huffman_encoded_bytes = data[header_length:]
    bitstring = unpack_bitstring(huffman_encoded_bytes)
    huffman_tree = build_huffman_tree_from_frequency(freq)
    rle_decoded = huffman_decode(bitstring, huffman_tree)
    mtf_decoded = rle_decode(rle_decoded)
    return bytes(mtf_decoded)

########################################
# Главные функции compress/decompress с флагом:
# Флаг: 0x01 - с BWT, 0x00 - без BWT
########################################
def compress(data: bytes, use_bwt: bool = True) -> bytes:
    if use_bwt:
        flag = b'\x01'
        body = compress_small(data)
    else:
        flag = b'\x00'
        body = compress_large(data)
    return flag + body

def decompress(data: bytes) -> bytes:
    flag = data[0]
    body = data[1:]
    if flag == 0x01:
        return decompress_small(body)
    else:
        return decompress_large(body)

if __name__ == '__main__':
    text = "Пример тестового сообщения для сжатия"
    original = text.encode('utf-8')
    compressed = compress(original, use_bwt=True)
    decompressed = decompress(compressed)
    print("Исходный текст:", text)
    print("Сжатый размер:", len(compressed), "байт")
    print("Восстановленный текст:", decompressed.decode('utf-8'))
    
    try:
        with open("image.jpg", "rb") as f:
            img_data = f.read()
        comp_img = compress(img_data, use_bwt=True)
        print("Изображение сжато, первые 50 байт:", comp_img[:50])
        decom_img = decompress(comp_img)
        with open("reconstructed_image.png", "wb") as f:
            f.write(decom_img)
        print("Изображение восстановлено и сохранено как 'reconstructed_image.png'")
    except Exception as e:
        print("Ошибка при обработке изображения:", e)
