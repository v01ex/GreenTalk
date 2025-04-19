"""
Улучшенный модуль для сжатия аудио в проекте GreenTalk
Специальная версия для MP3 и других форматов аудио
"""

def compress_audio(file_data, original_size):
    """
    Улучшенное сжатие аудио с дополнительными стратегиями для MP3 и других форматов
    
    Args:
        file_data (bytes): Бинарные данные аудиофайла
        original_size (int): Исходный размер в байтах
        
    Returns:
        dict: Результат сжатия с ключами 'data', 'size', 'ratio', 'method'
    """
    import zlib
    import sys
    import bz2
    import lzma
    
    print(f"Начало сжатия аудио, исходный размер: {original_size/1024:.2f} КБ")
    print(f"Тип данных file_data: {type(file_data)}")
    print(f"Длина данных: {len(file_data)} байт")
    print(f"Первые 20 байт: {file_data[:20]}")
    
    # Определяем тип файла по заголовку
    is_mp3 = False
    is_ogg = False
    is_wav = False
    is_webm = False
    
    if len(file_data) > 3:
        if file_data[:3] == b'ID3' or file_data[:2] == b'\xff\xfb':
            is_mp3 = True
            print("Обнаружен формат MP3")
        elif file_data[:4] == b'OggS':
            is_ogg = True
            print("Обнаружен формат Ogg Vorbis/Opus")
        elif file_data[:4] == b'RIFF' and file_data[8:12] == b'WAVE':
            is_wav = True
            print("Обнаружен формат WAV")
        elif file_data[:4] == b'\x1a\x45\xdf\xa3':
            is_webm = True
            print("Обнаружен формат WebM аудио")
    
    # Для сохранения лучшего результата
    best_result = {
        'data': file_data,
        'size': original_size,
        'ratio': 0,
        'method': 'original'
    }
    
    # Расширенная стратегия для MP3: сжимаем только метаданные
    if is_mp3:
        try:
            # Увеличиваем размер сжимаемой области метаданных
            header_size = min(204800, len(file_data) // 3)  # Увеличили до 200КБ
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            # Пробуем разные алгоритмы сжатия для метаданных
            compressions = [
                ('zlib-9', zlib.compress(header_data, level=9)),
                ('bz2', bz2.compress(header_data, compresslevel=9)),
                ('lzma', lzma.compress(header_data, preset=1))
            ]
            
            best_header = None
            best_size = len(header_data)
            best_algo = None
            
            for algo, comp_data in compressions:
                if len(comp_data) < best_size:
                    best_size = len(comp_data)
                    best_header = comp_data
                    best_algo = algo
                    
            if best_header and best_size < len(header_data):
                # Собираем файл обратно с лучшим сжатым заголовком
                combined_data = best_header + body_data
                combined_size = len(combined_data)
                
                if combined_size < original_size:
                    ratio = (1 - combined_size / original_size) * 100
                    print(f"Частичное сжатие MP3 ({best_algo}): {ratio:.2f}%")
                    best_result = {
                        'data': combined_data,
                        'size': combined_size,
                        'ratio': ratio,
                        'method': f'partial-mp3-{best_algo}'
                    }
                    print(f"Лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при частичном сжатии MP3: {e}")
    
    # Особая стратегия для WAV (несжатый формат)
    if is_wav:
        try:
            # WAV обычно хорошо сжимается целиком
            print("Попытка сжатия WAV полностью...")
            
            # Пробуем разные алгоритмы сжатия для WAV
            compressions = [
                ('zlib-9', zlib.compress(file_data, level=9)),
                ('bz2', bz2.compress(file_data, compresslevel=9)),
            ]
            
            for algo, comp_data in compressions:
                comp_size = len(comp_data)
                ratio = (1 - comp_size / original_size) * 100
                
                print(f"Сжатие WAV с {algo}: {ratio:.2f}%")
                
                if comp_size < original_size and ratio > best_result['ratio']:
                    best_result = {
                        'data': comp_data,
                        'size': comp_size,
                        'ratio': ratio,
                        'method': f'wav-{algo}'
                    }
                    print(f"Новый лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при сжатии WAV: {e}")
    
    # Стратегия для Ogg Vorbis/Opus
    if is_ogg:
        try:
            # Ogg - уже сжатый формат, пробуем небольшими блоками
            header_size = min(81920, len(file_data) // 4)  # 80KB
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            compressed_header = zlib.compress(header_data, level=9)
            
            if len(compressed_header) < len(header_data):
                combined_data = compressed_header + body_data
                combined_size = len(combined_data)
                
                if combined_size < original_size:
                    ratio = (1 - combined_size / original_size) * 100
                    print(f"Частичное сжатие Ogg: {ratio:.2f}%")
                    if ratio > best_result['ratio']:
                        best_result = {
                            'data': combined_data,
                            'size': combined_size,
                            'ratio': ratio,
                            'method': 'partial-ogg'
                        }
                        print(f"Лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при частичном сжатии Ogg: {e}")
    
    # Стратегия для WebM аудио
    if is_webm:
        try:
            # WebM аудио - особая структура, пробуем сжать заголовок
            header_size = min(102400, len(file_data) // 3)  # 100KB
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            # Пробуем разные алгоритмы сжатия для заголовка
            compressions = [
                ('zlib-9', zlib.compress(header_data, level=9)),
                ('bz2', bz2.compress(header_data, compresslevel=9)),
            ]
            
            best_header = None
            best_size = len(header_data)
            best_algo = None
            
            for algo, comp_data in compressions:
                if len(comp_data) < best_size:
                    best_size = len(comp_data)
                    best_header = comp_data
                    best_algo = algo
                    
            if best_header and best_size < len(header_data):
                combined_data = best_header + body_data
                combined_size = len(combined_data)
                
                if combined_size < original_size:
                    ratio = (1 - combined_size / original_size) * 100
                    print(f"Частичное сжатие WebM аудио ({best_algo}): {ratio:.2f}%")
                    if ratio > best_result['ratio']:
                        best_result = {
                            'data': combined_data,
                            'size': combined_size,
                            'ratio': ratio,
                            'method': f'partial-webm-{best_algo}'
                        }
                        print(f"Лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при частичном сжатии WebM: {e}")
    
    # Оптимизированное гибридное блочное сжатие для всех типов аудио
    block_sizes = [2048, 4096, 8192, 16384]  # Оптимальные размеры для аудио
    for block_size in block_sizes:
        try:
            print(f"Блочное сжатие аудио (размер блока: {block_size/1024:.1f} KB)...")
            compressed_blocks = bytearray()
            block_count = 0
            compressed_count = 0
            
            for i in range(0, len(file_data), block_size):
                block_count += 1
                block = file_data[i:i+block_size]
                
                # Пробуем разные алгоритмы сжатия для каждого блока
                best_block = block
                best_block_size = len(block)
                best_block_method = 0  # 0 - без сжатия
                
                try:
                    # zlib сжатие (быстрое)
                    zlib_block = zlib.compress(block, level=9)
                    if len(zlib_block) < best_block_size:
                        best_block = zlib_block
                        best_block_size = len(zlib_block)
                        best_block_method = 1  # 1 - zlib
                    
                    # bz2 сжатие (для больших блоков)
                    if len(block) > 512 and block_count % 3 == 0:  # Каждый 3-й блок
                        bz2_block = bz2.compress(block, compresslevel=9)
                        if len(bz2_block) < best_block_size:
                            best_block = bz2_block
                            best_block_size = len(bz2_block)
                            best_block_method = 2  # 2 - bz2
                    
                    # LZMA сжатие (для выборочных блоков аудио метаданных)
                    if i < len(file_data) // 4 and len(block) > 4096:  # Только для первой четверти файла
                        lzma_block = lzma.compress(block, preset=1)
                        if len(lzma_block) < best_block_size:
                            best_block = lzma_block
                            best_block_size = len(lzma_block)
                            best_block_method = 3  # 3 - lzma
                    
                    # Если блок сжался, считаем его успешно сжатым
                    if best_block_method > 0:
                        compressed_count += 1
                    
                    # Сохраняем метод сжатия (1 байт), размер блока (4 байта) и сам блок
                    compressed_blocks.extend(bytes([best_block_method]))
                    block_len = len(best_block)
                    compressed_blocks.extend(block_len.to_bytes(4, byteorder='little'))
                    compressed_blocks.extend(best_block)
                except Exception as e:
                    # Если ошибка компрессии, используем оригинальный блок
                    print(f"Ошибка при сжатии блока аудио {block_count}: {e}")
                    compressed_blocks.extend(bytes([0]))  # 0 - без сжатия
                    block_len = len(block)
                    compressed_blocks.extend(block_len.to_bytes(4, byteorder='little'))
                    compressed_blocks.extend(block)
            
            comp_size = len(compressed_blocks)
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"Блочное сжатие (блок {block_size}B): размер={comp_size/1024:.2f} КБ, сжатие={ratio:.2f}%, блоков={block_count}, сжато={compressed_count}")
            
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed_blocks,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': f'audio-blocks-{block_size}'
                }
                print(f"Новый лучший метод: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"Ошибка при блочном сжатии аудио ({block_size}): {e}")
    
    # Попытка сжатия BZ2 для всего файла
    if original_size < 30 * 1024 * 1024:  # До 30 МБ
        try:
            print(f"Попытка сжатия всего аудиофайла с BZ2...")
            compressed = bz2.compress(file_data, compresslevel=9)
            comp_size = len(compressed)
            ratio = (1 - comp_size / original_size) * 100
            
            print(f"BZ2 сжатие: {ratio:.2f}%")
            
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'bz2-9'
                }
                print(f"Новый лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при сжатии аудио с BZ2: {e}")
    
    # Попытка LZMA для маленьких файлов
    if original_size < 5 * 1024 * 1024:  # До 5 МБ
        try:
            print(f"Попытка сжатия аудио с LZMA...")
            compressed = lzma.compress(file_data, preset=1)
            comp_size = len(compressed)
            ratio = (1 - comp_size / original_size) * 100
            
            print(f"LZMA сжатие: {ratio:.2f}%")
            
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'lzma-1'
                }
                print(f"Новый лучший метод: {best_result['method']}")
        except Exception as e:
            print(f"Ошибка при сжатии аудио с LZMA: {e}")
    
    # Стандартное ZLIB сжатие для всех типов аудио
    levels = [1, 6, 9]
    for level in levels:
        try:
            print(f"Попытка сжатия аудио с zlib уровня {level}...")
            compressed = zlib.compress(file_data, level=level)
            comp_size = len(compressed)
            
            # Вычисляем коэффициент сжатия
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"zlib-{level}: размер после сжатия = {comp_size/1024:.2f} КБ, сжатие = {ratio:.2f}%")
            
            # Если получили лучшее сжатие, сохраняем результат
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': f'zlib-{level}'
                }
                print(f"Новый лучший метод: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"Ошибка при сжатии аудио с zlib-{level}: {e}")
    
    # АГРЕССИВНАЯ СТРАТЕГИЯ: если сжатие меньше 1%, все равно используем какое-то сжатие
    # (0.5% сжатия на больших файлах тоже экономия)
    if best_result['ratio'] < 1.0 and original_size > 100 * 1024:  # Для файлов больше 100KB
        try:
            # Пробуем zlib-1 (самый быстрый)
            compressed = zlib.compress(file_data, level=1)
            comp_size = len(compressed)
            ratio = (1 - comp_size / original_size) * 100
            
            if comp_size < original_size:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'zlib-minimal'
                }
                print(f"Применяем минимальное сжатие: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"Ошибка при минимальном сжатии: {e}")
    
    # Выводим итоговый результат
    print(f"=== РЕЗУЛЬТАТЫ СЖАТИЯ АУДИО ===")
    print(f"Исходный размер: {original_size/1024:.2f} КБ")
    print(f"Лучший метод: {best_result['method']}")
    print(f"Сжатый размер: {best_result['size']/1024:.2f} КБ")
    print(f"Степень сжатия: {best_result['ratio']:.2f}%")
    
    return best_result


def decompress_audio_blocks(compressed_data):
    """
    Декомпрессия аудио, сжатого блочным методом с поддержкой разных алгоритмов
    
    Args:
        compressed_data (bytes): Сжатые данные
        
    Returns:
        bytes: Распакованные данные
    """
    import zlib
    import bz2
    import lzma
    
    decompressed = bytearray()
    offset = 0
    
    print(f"Начало декомпрессии блочных данных аудио, размер: {len(compressed_data)/1024:.2f} КБ")
    
    while offset < len(compressed_data):
        try:
            # Получаем метод сжатия (1 байт)
            compression_method = compressed_data[offset]
            offset += 1
            
            # Получаем размер блока (4 байта)
            block_len = int.from_bytes(compressed_data[offset:offset+4], byteorder='little')
            offset += 4
            
            # Получаем сжатый блок
            compressed_block = compressed_data[offset:offset+block_len]
            offset += block_len
            
            # Распаковываем блок в зависимости от метода сжатия
            if compression_method == 0:
                # Несжатый блок
                decompressed_block = compressed_block
            elif compression_method == 1:
                # ZLIB
                decompressed_block = zlib.decompress(compressed_block)
            elif compression_method == 2:
                # BZ2
                decompressed_block = bz2.decompress(compressed_block)
            elif compression_method == 3:
                # LZMA
                decompressed_block = lzma.decompress(compressed_block)
            else:
                # Неизвестный метод, используем как несжатый
                print(f"Неизвестный метод сжатия блока: {compression_method}")
                decompressed_block = compressed_block
                
            decompressed.extend(decompressed_block)
        except Exception as e:
            print(f"Ошибка при декомпрессии блока аудио: {e}")
            # В случае ошибки просто добавляем оставшиеся данные как есть
            decompressed.extend(compressed_data[offset:])
            break
    
    print(f"Декомпрессия завершена, итоговый размер: {len(decompressed)/1024:.2f} КБ")
    return bytes(decompressed)


if __name__ == "__main__":
    # Тестирование функции
    import sys
    
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "rb") as f:
                test_data = f.read()
            
            print(f"Загружен файл размером {len(test_data)/1024:.2f} КБ")
            result = compress_audio(test_data, len(test_data))
            print(f"\nРезультаты сжатия:")
            print(f"Метод: {result['method']}")
            print(f"Размер: {result['size']/1024:.2f} КБ")
            print(f"Сжатие: {result['ratio']:.2f}%")
            
            # Если указан аргумент --save, сохраняем сжатый файл
            if "--save" in sys.argv:
                output_filename = sys.argv[1] + ".compressed"
                with open(output_filename, "wb") as f:
                    f.write(result['data'])
                print(f"Сжатый файл сохранен как {output_filename}")
            
        except Exception as e:
            print(f"Ошибка при тестировании: {e}")
    else:
        print("Использование: python audio_compression.py <файл> [--save]")