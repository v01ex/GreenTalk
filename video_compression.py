"""
Улучшенный модуль для сжатия видео в проекте GreenTalk
Специальная версия для MP4 и других форматов видео
"""

def compress_video(file_data, original_size):
    """
    Улучшенное сжатие видео с отладкой и стратегиями для разных форматов
    
    Args:
        file_data (bytes): Бинарные данные видеофайла
        original_size (int): Исходный размер в байтах
        
    Returns:
        dict: Результат сжатия с ключами 'data', 'size', 'ratio', 'method'
    """
    import zlib
    import sys
    import bz2
    import lzma
    
    print(f"DEBUG: Начинаем сжатие видео, размер: {original_size/1024:.2f} КБ")
    print(f"DEBUG: Тип данных file_data: {type(file_data)}")
    print(f"DEBUG: Длина file_data: {len(file_data)} байт")
    print(f"DEBUG: Первые 20 байт: {file_data[:20]}")
    
    # Проверяем сигнатуру файла для определения формата
    is_mp4 = False
    is_webm = False
    
    if len(file_data) > 16:
        if file_data[4:8] == b'ftyp':
            is_mp4 = True
            print("DEBUG: Обнаружен формат MP4")
        elif file_data.startswith(b'\x1a\x45\xdf\xa3'):
            is_webm = True
            print("DEBUG: Обнаружен формат WebM/MKV")
    
    # Для сохранения лучшего результата
    best_result = {
        'data': file_data,
        'size': original_size,
        'ratio': 0,
        'method': 'original'
    }
    
    # Расширенная стратегия для MP4
    if is_mp4:
        try:
            # Увеличиваем размер сжимаемой области метаданных
            header_size = min(262144, len(file_data) // 3)  # Увеличили до 256КБ
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            # Пробуем разные алгоритмы сжатия для метаданных
            compressions = [
                ('zlib-9', zlib.compress(header_data, level=9)),
                ('bz2', bz2.compress(header_data, compresslevel=9)),
                ('lzma', lzma.compress(header_data, preset=1))  # Preset 1 для баланса скорости/сжатия
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
                    print(f"DEBUG: Частичное сжатие MP4 ({best_algo}): {ratio:.2f}%")
                    best_result = {
                        'data': combined_data,
                        'size': combined_size,
                        'ratio': ratio,
                        'method': f'partial-mp4-{best_algo}'
                    }
                    print(f"DEBUG: Лучший метод обновлен на: {best_result['method']}")
        except Exception as e:
            print(f"DEBUG: Ошибка при частичном сжатии MP4: {e}")
    
    # Расширенная стратегия для WebM/MKV
    if is_webm:
        try:
            # Увеличиваем размер сжимаемой области метаданных
            header_size = min(409600, len(file_data) // 2)  # Увеличили до 400КБ
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
                    print(f"DEBUG: Частичное сжатие WebM/MKV ({best_algo}): {ratio:.2f}%")
                    if ratio > best_result['ratio']:
                        best_result = {
                            'data': combined_data,
                            'size': combined_size,
                            'ratio': ratio,
                            'method': f'partial-webm-{best_algo}'
                        }
                        print(f"DEBUG: Лучший метод обновлен на: {best_result['method']}")
        except Exception as e:
            print(f"DEBUG: Ошибка при частичном сжатии WebM/MKV: {e}")
    
    # Улучшенное гибридное блочное сжатие видео
    block_sizes = [4096, 8192, 16384, 32768, 65536]  # Больше вариантов размеров блоков
    for block_size in block_sizes:
        try:
            print(f"DEBUG: Блочное сжатие видео (размер блока: {block_size/1024:.1f} KB)...")
            
            compressed_blocks = bytearray()
            total_blocks = (len(file_data) + block_size - 1) // block_size
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
                    
                    # bz2 сжатие (лучшее сжатие для некоторых типов данных)
                    if len(block) > 512:  # bz2 требует минимальный размер
                        bz2_block = bz2.compress(block, compresslevel=9)
                        if len(bz2_block) < best_block_size:
                            best_block = bz2_block
                            best_block_size = len(bz2_block)
                            best_block_method = 2  # 2 - bz2
                    
                    # LZMA сжатие для избранных блоков (очень сильное сжатие)
                    # Применяем только для больших блоков из-за производительности
                    if len(block) > 8192 and block_count % 5 == 0:  # Каждый 5-й блок
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
                    print(f"DEBUG: Ошибка при сжатии блока {block_count}: {e}")
                    compressed_blocks.extend(bytes([0]))  # 0 - без сжатия
                    block_len = len(block)
                    compressed_blocks.extend(block_len.to_bytes(4, byteorder='little'))
                    compressed_blocks.extend(block)
            
            comp_size = len(compressed_blocks)
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"DEBUG: Блочное сжатие (блок {block_size}B): размер={comp_size/1024:.2f} КБ, сжатие={ratio:.2f}%, блоков={block_count}, сжато={compressed_count}")
            
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed_blocks,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': f'video-blocks-{block_size}'
                }
                print(f"DEBUG: Найден лучший метод сжатия: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"DEBUG: Ошибка при блочном сжатии видео ({block_size}): {e}")
    
    # Пробуем новые методы сжатия для всего файла
    try:
        print(f"DEBUG: Попытка сжатия видео с BZ2...")
        if len(file_data) < 50 * 1024 * 1024:  # Только для файлов меньше 50MB
            compressed = bz2.compress(file_data, compresslevel=9)
            comp_size = len(compressed)
            
            # Вычисляем коэффициент сжатия
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"DEBUG: bz2: размер после сжатия = {comp_size/1024:.2f} КБ, сжатие = {ratio:.2f}%")
            
            # Если получили лучшее сжатие, сохраняем результат
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'bz2-9'
                }
                print(f"DEBUG: Найден лучший метод сжатия (пока): {best_result['method']} с {best_result['ratio']:.2f}%")
    except Exception as e:
        print(f"DEBUG: Ошибка при сжатии видео с bz2: {e}")
    
    try:
        print(f"DEBUG: Попытка сжатия видео с LZMA (для небольших файлов)...")
        if len(file_data) < 20 * 1024 * 1024:  # Только для файлов меньше 20MB
            compressed = lzma.compress(file_data, preset=1)
            comp_size = len(compressed)
            
            # Вычисляем коэффициент сжатия
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"DEBUG: lzma: размер после сжатия = {comp_size/1024:.2f} КБ, сжатие = {ratio:.2f}%")
            
            # Если получили лучшее сжатие, сохраняем результат
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'lzma-1'
                }
                print(f"DEBUG: Найден лучший метод сжатия (пока): {best_result['method']} с {best_result['ratio']:.2f}%")
    except Exception as e:
        print(f"DEBUG: Ошибка при сжатии видео с lzma: {e}")
    
    # Попробуем обычное zlib с разными уровнями для всех форматов
    levels = [1, 6, 9]
    for level in levels:
        try:
            print(f"DEBUG: Попытка сжатия видео с zlib уровня {level}...")
            compressed = zlib.compress(file_data, level=level)
            comp_size = len(compressed)
            
            # Вычисляем коэффициент сжатия
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            print(f"DEBUG: zlib-{level}: размер после сжатия = {comp_size/1024:.2f} КБ, сжатие = {ratio:.2f}%")
            
            # Если получили лучшее сжатие, сохраняем результат
            if comp_size < original_size and ratio > best_result['ratio']:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': f'zlib-{level}'
                }
                print(f"DEBUG: Найден лучший метод сжатия (пока): {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"DEBUG: Ошибка при сжатии видео с zlib-{level}: {e}")
    
    # Если все стратегии не дали результата, 
    # попробуем сжать хотя бы немного с mimimum-ratio = 0
    if best_result['ratio'] == 0 and original_size > 1000000:  # Только для файлов > 1MB
        try:
            print(f"DEBUG: Последняя попытка сжатия видео с zlib уровня 1 (минимальный)...")
            compressed = zlib.compress(file_data, level=1)
            comp_size = len(compressed)
            
            # Вычисляем коэффициент сжатия
            ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
            
            # Даже если сжатие очень маленькое, но положительное, используем его
            if comp_size < original_size:
                best_result = {
                    'data': compressed,
                    'size': comp_size,
                    'ratio': ratio,
                    'method': 'zlib-minimal'
                }
                print(f"DEBUG: Найдено минимальное сжатие: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"DEBUG: Ошибка при минимальном сжатии видео: {e}")
    
    # Выводим итоговый результат
    print(f"DEBUG: ИТОГОВОЕ СЖАТИЕ ВИДЕО: метод={best_result['method']}, степень={best_result['ratio']:.2f}%")
    return best_result


def decompress_video_blocks(compressed_data):
    """
    Декомпрессия видео, сжатого блочным методом с поддержкой разных алгоритмов
    
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
    
    print(f"DEBUG: Начало декомпрессии блочных данных видео, размер: {len(compressed_data)/1024:.2f} КБ")
    
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
                print(f"DEBUG: Неизвестный метод сжатия блока: {compression_method}")
                decompressed_block = compressed_block
                
            decompressed.extend(decompressed_block)
        except Exception as e:
            print(f"DEBUG: Ошибка при декомпрессии блока видео: {e}")
            # В случае ошибки просто добавляем оставшиеся данные как есть
            decompressed.extend(compressed_data[offset:])
            break
    
    print(f"DEBUG: Декомпрессия завершена, итоговый размер: {len(decompressed)/1024:.2f} КБ")
    return bytes(decompressed)


if __name__ == "__main__":
    # Тестирование функции
    import sys
    
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "rb") as f:
                test_data = f.read()
            
            print(f"Загружен файл размером {len(test_data)/1024:.2f} КБ")
            result = compress_video(test_data, len(test_data))
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
        print("Использование: python video_compression.py <файл> [--save]")