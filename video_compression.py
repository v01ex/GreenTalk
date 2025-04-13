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
    
    # Разные стратегии для разных форматов
    if is_mp4:
        # MP4 обычно плохо сжимается, пробуем только головную часть файла
        # Так как медиа-данные уже сжаты, но метаданные могут быть сжаты
        try:
            # Сжимаем только первые 128КБ (метаданные)
            header_size = min(131072, len(file_data) // 4)
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            compressed_header = zlib.compress(header_data, level=9)
            
            # Собираем файл обратно
            combined_data = compressed_header + body_data
            combined_size = len(combined_data)
            
            if combined_size < original_size:
                ratio = (1 - combined_size / original_size) * 100
                print(f"DEBUG: Частичное сжатие MP4: {ratio:.2f}%")
                best_result = {
                    'data': combined_data,
                    'size': combined_size,
                    'ratio': ratio,
                    'method': 'partial-mp4'
                }
                print(f"DEBUG: Лучший метод обновлен на: {best_result['method']}")
        except Exception as e:
            print(f"DEBUG: Ошибка при частичном сжатии MP4: {e}")
    
    # Специальная стратегия для WebM/MKV
    if is_webm:
        try:
            # Для WebM пробуем сжать первые 200КБ (метаданные)
            header_size = min(204800, len(file_data) // 3)
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            compressed_header = zlib.compress(header_data, level=9)
            
            # Собираем файл обратно
            combined_data = compressed_header + body_data
            combined_size = len(combined_data)
            
            if combined_size < original_size:
                ratio = (1 - combined_size / original_size) * 100
                print(f"DEBUG: Частичное сжатие WebM/MKV: {ratio:.2f}%")
                if ratio > best_result['ratio']:
                    best_result = {
                        'data': combined_data,
                        'size': combined_size,
                        'ratio': ratio,
                        'method': 'partial-webm'
                    }
                    print(f"DEBUG: Лучший метод обновлен на: {best_result['method']}")
        except Exception as e:
            print(f"DEBUG: Ошибка при частичном сжатии WebM/MKV: {e}")
    
    # Попробуем блочное сжатие видео с более мелкими блоками
    block_sizes = [4096, 16384, 65536]  # Попробуем несколько размеров блоков
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
                try:
                    compressed_block = zlib.compress(block, level=9)
                    # Если блок не сжимается хорошо, используем оригинал
                    if len(compressed_block) >= len(block):
                        compressed_block = block
                        flag = 0  # Флаг "несжатый блок"
                    else:
                        flag = 1  # Флаг "сжатый блок"
                        compressed_count += 1
                    
                    # Сохраняем флаг (1 байт), размер блока (4 байта) и сам блок
                    compressed_blocks.extend(bytes([flag]))
                    block_len = len(compressed_block)
                    compressed_blocks.extend(block_len.to_bytes(4, byteorder='little'))
                    compressed_blocks.extend(compressed_block)
                except Exception as e:
                    # Если ошибка компрессии, используем оригинальный блок
                    flag = 0
                    print(f"DEBUG: Ошибка при сжатии блока {block_count}: {e}")
                    compressed_blocks.extend(bytes([flag]))
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

    # Выводим УСИЛЕННОЕ логирование для диагностики
    print(f"=== РЕЗУЛЬТАТЫ СЖАТИЯ ВИДЕО ===")
    print(f"Исходный размер: {original_size/1024:.2f} КБ")
    print(f"Лучший метод: {best_result['method']}")
    print(f"Сжатый размер: {best_result['size']/1024:.2f} КБ")
    print(f"Степень сжатия: {best_result['ratio']:.2f}%")
    
    return best_result


def decompress_video_blocks(compressed_data):
    """
    Декомпрессия видео, сжатого блочным методом
    
    Args:
        compressed_data (bytes): Сжатые данные
        
    Returns:
        bytes: Распакованные данные
    """
    import zlib
    
    decompressed = bytearray()
    offset = 0
    
    print(f"DEBUG: Начало декомпрессии блочных данных видео, размер: {len(compressed_data)/1024:.2f} КБ")
    
    while offset < len(compressed_data):
        try:
            # Получаем флаг (1 байт)
            flag = compressed_data[offset]
            offset += 1
            
            # Получаем размер блока (4 байта)
            block_len = int.from_bytes(compressed_data[offset:offset+4], byteorder='little')
            offset += 4
            
            # Проверка на валидность размера блока
            if block_len <= 0 or block_len > len(compressed_data):
                print(f"DEBUG: Некорректный размер блока: {block_len}")
                # В случае ошибки просто добавляем оставшиеся данные как есть
                decompressed.extend(compressed_data[offset-5:])
                break
            
            # Получаем сжатый блок
            compressed_block = compressed_data[offset:offset+block_len]
            offset += block_len
            
            # Распаковываем блок в зависимости от флага
            if flag == 1:
                # Сжатый блок
                try:
                    decompressed_block = zlib.decompress(compressed_block)
                    decompressed.extend(decompressed_block)
                except Exception as e:
                    print(f"DEBUG: Ошибка при декомпрессии блока видео: {e}")
                    # При ошибке используем блок как есть
                    decompressed.extend(compressed_block)
            else:
                # Несжатый блок
                decompressed.extend(compressed_block)
            
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