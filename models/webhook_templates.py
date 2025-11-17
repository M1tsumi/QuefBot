from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class WebhookTemplate:
    name: str
    json_payload: str


class TemplateStore:
    def __init__(self) -> None:
        self._templates: Dict[str, WebhookTemplate] = {}

    def set_template(self, name: str, json_payload: str) -> None:
        key = name.lower()
        self._templates[key] = WebhookTemplate(name=name, json_payload=json_payload)

    def get_template(self, name: str) -> Optional[WebhookTemplate]:
        key = name.lower()
        return self._templates.get(key)

    def all_names(self) -> List[str]:
        return [template.name for template in self._templates.values()]
