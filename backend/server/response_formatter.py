"""
Модуль для форматирования ответов от браузер-агента.
Преобразует технические данные и JSON в читаемый текст.
"""

import json
import re
from typing import Dict, Any, List, Union


def format_results(result: str) -> str:
    """
    Форматирует ответ браузер-агента в читаемый текст
    
    Args:
        result: Строка ответа от браузер-агента
        
    Returns:
        Отформатированная строка для отображения пользователю
    """
    try:
        # Сначала проверяем, содержит ли текст эмодзи действий браузера
        if any(emoji in result for emoji in ['🔗', '🖱️', '🔍', '📄', '⌨️']):
            return format_browser_actions(result)

        # Проверяем, содержит ли строка JSON
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            try:
                json_data = json.loads(json_match.group(0))
                
                # Обрабатываем разные типы данных
                if 'relevant_articles' in json_data:
                    return format_articles(json_data)
                
                if 'startups' in json_data:
                    return format_startups(json_data['startups'])
                
                if 'articles' in json_data:
                    return format_articles_list(json_data['articles'])
                
                # Общий случай - форматируем любую структуру JSON
                return format_generic_object(json_data)
            except json.JSONDecodeError:
                # Ошибка при парсинге JSON, просто продолжаем
                pass
        
        # Если не удалось определить формат, очищаем от Markdown и возвращаем
        return clean_markdown(result)
    except Exception as e:
        # В случае любой ошибки возвращаем оригинальный текст, очищенный от Markdown
        return clean_markdown(result)


def format_browser_actions(result: str) -> str:
    """
    Форматирует действия браузера и извлеченную информацию в читаемый текст
    
    Args:
        result: Строка с действиями браузера
        
    Returns:
        Форматированный текст с описанием действий и результатами
    """
    # Разделяем текст на строки
    lines = result.split('\n')
    formatted_text = ''
    data_section = ''
    is_in_data_section = False
    collected_json = ''
    
    # Обрабатываем каждую строку
    for line in lines:
        line = line.strip()
        
        # Пропускаем пустые строки
        if not line:
            continue
        
        # Определяем начало блока данных
        if 'Extracted from page' in line or '📄' in line:
            is_in_data_section = True
            data_section = 'Найденная информация:\n'
            continue
        
        # Если мы внутри секции данных, накапливаем JSON
        if is_in_data_section:
            if line.startswith('{') or line.startswith('[') or \
               '"title":' in line or '"link":' in line:
                collected_json += line + '\n'
            elif 'The task' in line:
                # Финальное сообщение после данных
                is_in_data_section = False
                formatted_text += data_section + '\n' + line
            continue
        
        # Форматируем действия браузера
        if '🔗' in line:
            formatted_text += f"Перешел на сайт: {line.split('🔗')[1].strip()}\n"
        elif '🖱️' in line:
            formatted_text += f"Нажал: {line.split('🖱️')[1].strip()}\n"
        elif '🔍' in line:
            formatted_text += f"{line.split('🔍')[1].strip()}\n"
        elif '⌨️' in line:
            formatted_text += f"Ввел: {line.split('⌨️')[1].strip()}\n"
        elif '🕒' in line:
            formatted_text += f"Ожидание: {line.split('🕒')[1].strip()}\n"
        elif not any(x in line for x in ['📄', '```', 'Extracted from page']) and \
             not line.startswith('}') and not line.startswith(']'):
            # Добавляем обычный текст (не JSON и не служебные строки)
            formatted_text += f"{line}\n"
    
    # Обрабатываем собранный JSON
    if collected_json:
        try:
            # Ищем начало и конец JSON-структуры
            start_bracket = collected_json.find('[')
            end_bracket = collected_json.rfind(']')
            
            if start_bracket != -1 and end_bracket != -1:
                articles_json = collected_json[start_bracket:end_bracket + 1]
                articles = json.loads(articles_json)
                data_section += format_articles_simple(articles)
            else:
                # Если это не массив, проверяем другие структуры
                start_brace = collected_json.find('{')
                end_brace = collected_json.rfind('}')
                
                if start_brace != -1 and end_brace != -1:
                    data_json = collected_json[start_brace:end_brace + 1]
                    data = json.loads(data_json)
                    
                    if 'articles' in data:
                        data_section += format_articles_list(data['articles'])
                    elif 'startups' in data:
                        data_section += format_startups(data['startups'])
                    else:
                        data_section += format_generic_object(data)
        except json.JSONDecodeError:
            # Если не удалось разобрать JSON, просто добавляем текст как есть
            data_section += "Не удалось обработать данные в структурированном формате."
        
        # Заменяем секцию данных в форматированном тексте
        if 'Найденная информация:' in formatted_text:
            formatted_text = formatted_text.replace('Найденная информация:', data_section)
        else:
            formatted_text += '\n' + data_section
    
    # Добавляем итоговое сообщение, если оно есть и еще не добавлено
    if 'The task' in result and 'The task' not in formatted_text:
        task_end_index = result.rfind('The task')
        if task_end_index != -1:
            task_message = result[task_end_index:].split('\n')[0].strip()
            formatted_text += f"\n\n{task_message}"
    
    return formatted_text.strip()


def format_articles_simple(articles: List[Dict]) -> str:
    """
    Простое форматирование списка статей без вложенной структуры
    
    Args:
        articles: Список статей
        
    Returns:
        Отформатированный текст со списком статей
    """
    if not isinstance(articles, list) or not articles:
        return "Статьи не найдены"
    
    formatted_text = ""
    
    for index, article in enumerate(articles):
        formatted_text += f"{index + 1}. {article.get('title', 'Без названия')}\n"
        
        if link := article.get('link') or article.get('url'):
            formatted_text += f"   Ссылка: {link}\n"
        
        if date := article.get('date'):
            formatted_text += f"   Дата: {date}\n"
        
        formatted_text += '\n'
    
    return formatted_text


def format_articles_list(articles: List[Dict]) -> str:
    """
    Форматирует список статей с возможными вложенными структурами
    
    Args:
        articles: Список статей
        
    Returns:
        Отформатированный текст со списком статей
    """
    if not isinstance(articles, list) or not articles:
        return "Статьи не найдены"
    
    formatted_text = ""
    
    for index, article in enumerate(articles):
        formatted_text += f"{index + 1}. {article.get('title', 'Без названия')}\n"
        
        if link := article.get('link') or article.get('url'):
            formatted_text += f"   Ссылка: {link}\n"
        
        if date := article.get('date'):
            formatted_text += f"   Дата: {date}\n"
        
        # Обработка вложенных ссылок
        if links := article.get('links'):
            if isinstance(links, list):
                formatted_text += f"   Связанные ссылки:\n"
                for link_index, link in enumerate(links):
                    formatted_text += f"     {link_index + 1}. {link}\n"
        
        formatted_text += '\n'
    
    return formatted_text


def format_articles(json_data: Dict) -> str:
    """
    Форматирует список статей из структуры с relevant_articles
    
    Args:
        json_data: Данные со статьями
        
    Returns:
        Отформатированный текст со списком статей
    """
    formatted_text = "Найденные статьи:\n\n"
    
    for index, article in enumerate(json_data['relevant_articles']):
        formatted_text += f"{index + 1}. {article.get('title', '')}\n"
        
        if date := article.get('date'):
            formatted_text += f"   Дата: {date}\n"
        
        formatted_text += '\n'
    
    if summary := json_data.get('summary'):
        formatted_text += f"\nКраткий обзор: {summary}"
    
    return formatted_text


def format_startups(startups: List[Dict]) -> str:
    """
    Форматирует список стартапов
    
    Args:
        startups: Список стартапов
        
    Returns:
        Отформатированный текст со списком стартапов
    """
    if not isinstance(startups, list) or not startups:
        return "Стартапы не найдены"
    
    formatted_text = "Найденные стартапы:\n\n"
    
    for index, startup in enumerate(startups):
        formatted_text += f"{index + 1}. {startup.get('title', 'Без названия')}\n"
        
        if link := startup.get('url') or startup.get('link'):
            formatted_text += f"   Ссылка: {link}\n"
        
        formatted_text += '\n'
    
    return formatted_text


def format_generic_object(obj: Union[Dict, List, Any]) -> str:
    """
    Универсальное форматирование объекта JSON в читаемый текст
    
    Args:
        obj: Объект данных
        
    Returns:
        Отформатированный текст
    """
    if not isinstance(obj, (dict, list)) or (isinstance(obj, list) and not obj):
        return str(obj)
    
    if isinstance(obj, list):
        formatted_text = ""
        for index, item in enumerate(obj):
            formatted_text += f"{index + 1}. "
            
            if isinstance(item, dict):
                sub_items = []
                for key, value in item.items():
                    if key in ['raw_html', 'html']:
                        continue
                    
                    if isinstance(value, str):
                        sub_items.append(f"{key}: {value}")
                    else:
                        sub_items.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
                
                formatted_text += ", ".join(sub_items)
            else:
                formatted_text += str(item)
            
            formatted_text += '\n'
        
        return formatted_text
    
    # Для словарей
    result = []
    for key, value in obj.items():
        if key in ['raw_html', 'html']:
            continue
        
        if isinstance(value, str):
            result.append(f"{key}: {value}")
        elif isinstance(value, list):
            formatted_list = format_generic_object(value)
            result.append(f"{key}:\n{formatted_list}")
        elif isinstance(value, dict):
            formatted_dict = format_generic_object(value)
            result.append(f"{key}:\n{formatted_dict}")
        else:
            result.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    
    return '\n\n'.join(result)


def clean_markdown(text: str) -> str:
    """
    Удаляет Markdown и другую техническую разметку из текста
    
    Args:
        text: Исходный текст с разметкой
        
    Returns:
        Очищенный текст
    """
    # Удаляем блоки кода
    text = re.sub(r'```[a-z]*\n', '', text)
    text = re.sub(r'```\n?', '', text)
    
    # Убираем пробелы перед скобками
    text = re.sub(r'^\s*\{', '{', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\}', '}', text, flags=re.MULTILINE)
    
    # Удаляем Markdown форматирование
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Жирный текст
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Курсив
    text = re.sub(r'#{1,6}\s+', '', text)         # Заголовки
    
    # Удаляем специфические маркеры
    text = re.sub(r'Extracted from page[^\n]*\n', '', text)
    text = re.sub(r'📄[^\n]*\n', '', text)
    
    # Исправляем неправильные JSON-структуры
    text = re.sub(r'\]\n\n+\]', ']]', text)
    
    # Убираем лишние пустые строки
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text 