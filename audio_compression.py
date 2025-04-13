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
    
    print(f"Начало сжатия аудио, исходный размер: {original_size/1024:.2f} КБ")
    
    # Определяем тип файла по заголовку
    is_mp3 = False
    if len(file_data) > 3 and (file_data[:3] == b'ID3' or file_data[:2] == b'\xff\xfb'):
        is_mp3 = True
        print("Обнаружен формат MP3")
    
    # Для сохранения лучшего результата
    best_result = {
        'data': file_data,
        'size': original_size,
        'ratio': 0,
        'method': 'original'
    }
    
    # Стратегия для MP3: сжимаем только метаданные
    if is_mp3:
        try:
            # Обычно метаданные находятся в начале MP3 файла
            # Попробуем сжать только первые 100KB
            header_size = min(102400, len(file_data) // 5)
            header_data = file_data[:header_size]
            body_data = file_data[header_size:]
            
            compressed_header = zlib.compress(header_data, level=9)
            combined_data = compressed_header + body_data
            combined_size = len(combined_data)
            
            if combined_size < original_size:
                ratio = (1 - combined_size / original_size) * 100
                print(f"Частичное сжатие MP3: {ratio:.2f}%")
                best_result = {
                    'data': combined_data,
                    'size': combined_size,
                    'ratio': ratio,
                    'method': 'partial-mp3'
                }
        except Exception as e:
            print(f"Ошибка при частичном сжатии MP3: {e}")
    
    # Попробуем блочное сжатие с разными размерами блоков
    block_sizes = [4096, 16384, 65536]
    for block_size in block_sizes:
        try:
            print(f"Блочное сжатие аудио (размер блока: {block_size/1024:.1f} KB)...")
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
                    compressed_blocks.extend(bytes([flag]))
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
                    'method': f'zlib-blocks-{block_size}'
                }
                print(f"Найден лучший метод сжатия: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"Ошибка при блочном сжатии аудио ({block_size}): {e}")
    
    # Простое zlib сжатие для всех типов аудио
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
                print(f"Найден лучший метод сжатия: {best_result['method']} с {best_result['ratio']:.2f}%")
        except Exception as e:
            print(f"Ошибка при сжатии аудио с zlib-{level}: {e}")
    
    # Выводим УСИЛЕННОЕ логирование для диагностики
    print(f"=== РЕЗУЛЬТАТЫ СЖАТИЯ АУДИО ===")
    print(f"Исходный размер: {original_size/1024:.2f} КБ")
    print(f"Лучший метод: {best_result['method']}")
    print(f"Сжатый размер: {best_result['size']/1024:.2f} КБ")
    print(f"Степень сжатия: {best_result['ratio']:.2f}%")
    
    return best_result


def decompress_audio_blocks(compressed_data):
    """
    Декомпрессия аудио, сжатого блочным методом с поддержкой флагов
    
    Args:
        compressed_data (bytes): Сжатые данные
        
    Returns:
        bytes: Распакованные данные
    """
    import zlib
    
    decompressed = bytearray()
    offset = 0
    
    print(f"Начало декомпрессии блочных данных аудио, размер: {len(compressed_data)/1024:.2f} КБ")
    
    while offset < len(compressed_data):
        try:
            # Получаем флаг (1 байт)
            flag = compressed_data[offset]
            offset += 1
            
            # Получаем размер блока (4 байта)
            block_len = int.from_bytes(compressed_data[offset:offset+4], byteorder='little')
            offset += 4
            
            # Получаем сжатый блок
            compressed_block = compressed_data[offset:offset+block_len]
            offset += block_len
            
            # Распаковываем блок в зависимости от флага
            if flag == 1:
                # Сжатый блок
                decompressed_block = zlib.decompress(compressed_block)
            else:
                # Несжатый блок
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