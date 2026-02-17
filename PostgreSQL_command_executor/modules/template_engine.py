"""
Модуль для рендеринга SQL-шаблонов с использованием Jinja2.
"""
from jinja2 import Template, StrictUndefined

def render_sql(template_str: str, context: dict) -> str:
    """
    Заполняет шаблон данными. 
    StrictUndefined вызовет ошибку, если в шаблоне есть переменная, которой нет в context.
    """
    template = Template(template_str, undefined=StrictUndefined)
    return template.render(**context)