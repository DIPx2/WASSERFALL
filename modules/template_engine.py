"""
Модуль рендеринга SQL-шаблонов с использованием движка Jinja2.
Преобразует текстовые шаблоны запросов в исполняемый SQL путём подстановки переменных.
"""
from jinja2 import Template, StrictUndefined


def render_sql(template_str: str, context: dict) -> str:
    """
    Сгенерировать итоговый SQL-запрос из шаблона.
    
    Аргументы:
        template_str: Исходный текст SQL-шаблона с синтаксисом Jinja2
        context: Словарь переменных для подстановки в шаблон
    
    Возвращает:
        Готовый SQL-запрос с заменёнными переменными
    """
    template = Template(template_str, undefined=StrictUndefined)
    return template.render(**context)