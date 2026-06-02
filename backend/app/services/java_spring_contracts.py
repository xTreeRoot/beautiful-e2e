from __future__ import annotations

import re
from pathlib import Path
from typing import Any


IGNORED_JAVA_DIRS = {".git", ".venv", "__pycache__", "build", "dist", "node_modules", "target"}

SCALAR_JAVA_TYPES = {
    "String": "string",
    "Long": "integer",
    "long": "integer",
    "Integer": "integer",
    "int": "integer",
    "Short": "integer",
    "short": "integer",
    "BigInteger": "integer",
    "Double": "number",
    "double": "number",
    "Float": "number",
    "float": "number",
    "BigDecimal": "number",
    "Boolean": "boolean",
    "boolean": "boolean",
    "LocalDate": "string",
    "LocalDateTime": "string",
    "Date": "string",
}


class JavaSpringContractExtractor:
    """从 Spring Controller 方法签名和 DTO 字段中提取接口参数契约。

    仓库扫描不能只看到 URL，否则模型会按通用分页习惯猜 `current/size/keyword`。
    这里把 `@RequestBody` 指向的 Java DTO 字段带进路由目录，作为生成 DSL 的事实边界。
    """

    def __init__(self) -> None:
        self._java_file_cache: dict[tuple[str, str], Path | None] = {}
        self._class_contract_cache: dict[tuple[str, str], dict[str, Any] | None] = {}

    def extract_handler_contract(
        self,
        root: Path,
        content: str,
        handler_index: int | None,
        rel: str,
    ) -> dict[str, Any]:
        if handler_index is None:
            return {}

        lines = content.splitlines()
        signature = self._handler_signature(lines, handler_index)
        parameters_text = self._method_parameters(signature)
        if not parameters_text:
            return {}

        imports = self._imports(content)
        package = self._package(content)
        route_parameters: list[dict[str, Any]] = []
        request_body: dict[str, Any] | None = None

        for raw_param in self._split_parameters(parameters_text):
            parsed = self._parse_parameter(raw_param)
            if not parsed:
                continue

            annotation_names = {name.split(".")[-1] for name, _attrs in parsed["annotations"]}
            if "PathVariable" in annotation_names:
                route_parameters.append(
                    self._single_parameter(parsed, "path", required=True, root=root, rel=rel)
                )
            elif "RequestParam" in annotation_names:
                required = self._annotation_attr(parsed, "RequestParam", "required") != "false"
                route_parameters.append(
                    self._single_parameter(parsed, "query", required=required, root=root, rel=rel)
                )
            elif "ParameterObject" in annotation_names:
                route_parameters.extend(
                    self._object_parameters(root, parsed["java_type"], imports, package, rel)
                )
            elif "RequestBody" in annotation_names:
                required = self._annotation_attr(parsed, "RequestBody", "required") != "false"
                request_body = self._request_body(root, parsed["java_type"], imports, package, required)

        result: dict[str, Any] = {}
        if route_parameters:
            result["parameters"] = route_parameters
        if request_body:
            result["request_body"] = request_body
        return result

    def _handler_signature(self, lines: list[str], handler_index: int) -> str:
        parts: list[str] = []
        depth = 0
        for cursor in range(handler_index, min(len(lines), handler_index + 12)):
            line = lines[cursor].strip()
            if not line:
                continue
            parts.append(line)
            depth += line.count("(") - line.count(")")
            if "{" in line and depth <= 0:
                break
        return " ".join(parts)

    def _method_parameters(self, signature: str) -> str:
        start = signature.find("(")
        if start < 0:
            return ""
        depth = 0
        for index, char in enumerate(signature[start:], start=start):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return signature[start + 1 : index]
        return ""

    def _split_parameters(self, parameters_text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        angle_depth = 0
        paren_depth = 0
        for index, char in enumerate(parameters_text):
            if char == "<":
                angle_depth += 1
            elif char == ">" and angle_depth:
                angle_depth -= 1
            elif char == "(":
                paren_depth += 1
            elif char == ")" and paren_depth:
                paren_depth -= 1
            elif char == "," and angle_depth == 0 and paren_depth == 0:
                parts.append(parameters_text[start:index].strip())
                start = index + 1
        tail = parameters_text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _parse_parameter(self, raw_param: str) -> dict[str, Any] | None:
        annotations = re.findall(r"@([\w.]+)(?:\(([^)]*)\))?", raw_param)
        cleaned = re.sub(r"@[\w.]+(?:\([^)]*\))?\s*", "", raw_param)
        cleaned = re.sub(r"\bfinal\s+", "", cleaned).strip()
        tokens = cleaned.split()
        if len(tokens) < 2:
            return None
        return {
            "annotations": annotations,
            "java_type": tokens[-2],
            "name": tokens[-1].removesuffix("..."),
        }

    def _single_parameter(
        self,
        parsed: dict[str, Any],
        location: str,
        *,
        required: bool,
        root: Path,
        rel: str,
    ) -> dict[str, Any]:
        name = (
            self._annotation_attr(parsed, "PathVariable", "value")
            or self._annotation_attr(parsed, "PathVariable", "name")
            or self._annotation_attr(parsed, "RequestParam", "value")
            or self._annotation_attr(parsed, "RequestParam", "name")
            or parsed["name"]
        )
        return {
            "name": name,
            "in": location,
            "required": required,
            "schema": self._schema_for_java_type(parsed["java_type"]),
            "source": rel,
        }

    def _annotation_attr(
        self,
        parsed: dict[str, Any],
        annotation_name: str,
        attr_name: str,
    ) -> str | None:
        for name, attrs in parsed["annotations"]:
            if name.split(".")[-1] != annotation_name:
                continue
            quoted = re.search(rf"{attr_name}\s*=\s*\"([^\"]+)\"", attrs)
            if quoted:
                return quoted.group(1)
            bare = re.fullmatch(r"\s*\"([^\"]+)\"\s*", attrs)
            if bare and attr_name == "value":
                return bare.group(1)
            literal = re.search(rf"{attr_name}\s*=\s*([A-Za-z0-9_.-]+)", attrs)
            if literal:
                return literal.group(1)
        return None

    def _object_parameters(
        self,
        root: Path,
        java_type: str,
        imports: dict[str, str],
        package: str | None,
        rel: str,
    ) -> list[dict[str, Any]]:
        contract = self._class_contract(root, java_type, imports, package, seen=set())
        if not contract:
            return []
        parameters: list[dict[str, Any]] = []
        for name, schema in contract["properties"].items():
            parameters.append(
                {
                    "name": name,
                    "in": "query",
                    "required": name in contract.get("required", []),
                    "schema": schema,
                    "source": schema.get("source") or rel,
                }
            )
        return parameters

    def _request_body(
        self,
        root: Path,
        java_type: str,
        imports: dict[str, str],
        package: str | None,
        required: bool,
    ) -> dict[str, Any] | None:
        contract = self._class_contract(root, java_type, imports, package, seen=set())
        if not contract:
            return None
        body: dict[str, Any] = {
            "required": required,
            "content_type": "application/json",
            "java_type": self._simple_type(java_type),
            "schema": {
                "type": "object",
                "properties": contract["properties"],
                "required": contract.get("required", []),
            },
            "source": contract.get("source"),
        }
        example = self._example_from_contract(contract)
        if example:
            body["example"] = example
        return body

    def _class_contract(
        self,
        root: Path,
        java_type: str,
        imports: dict[str, str],
        package: str | None,
        *,
        seen: set[str],
    ) -> dict[str, Any] | None:
        simple_type = self._simple_type(java_type)
        cache_key = (str(root), self._qualified_name(simple_type, imports, package))
        if cache_key in self._class_contract_cache:
            return self._class_contract_cache[cache_key]
        if simple_type in seen:
            return None
        seen.add(simple_type)

        class_path = self._resolve_java_file(root, simple_type, imports, package)
        if class_path is None:
            self._class_contract_cache[cache_key] = None
            return None

        try:
            content = class_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            self._class_contract_cache[cache_key] = None
            return None

        class_imports = self._imports(content)
        class_package = self._package(content)
        rel = self._relative_source(root, class_path)
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []

        extends_match = re.search(r"\bclass\s+\w+\s+extends\s+([A-Za-z_][\w.]*)", content)
        if extends_match:
            parent = self._class_contract(
                root,
                extends_match.group(1),
                class_imports,
                class_package,
                seen=seen,
            )
            if parent:
                properties.update(parent["properties"])
                required.extend(parent.get("required", []))

        for field in self._fields(content, rel):
            properties[field["name"]] = field["schema"]
            if field["required"] and field["name"] not in required:
                required.append(field["name"])

        contract = {"properties": properties, "required": required, "source": rel}
        self._class_contract_cache[cache_key] = contract
        return contract

    def _fields(self, content: str, rel: str) -> list[dict[str, Any]]:
        lines = content.splitlines()
        fields: list[dict[str, Any]] = []
        field_pattern = re.compile(
            r"\bprivate\s+(?!static\b)(?:final\s+)?(?P<type>[\w<>, ?\[\].]+)\s+"
            r"(?P<name>[A-Za-z_][\w]*)\s*(?:=[^;]+)?;"
        )
        for index, raw_line in enumerate(lines):
            line = raw_line.strip()
            if " static " in f" {line} ":
                continue
            match = field_pattern.search(line)
            if not match:
                continue
            context = self._field_annotation_context(lines, index)
            if re.search(r"@Schema\([^)]*hidden\s*=\s*true", context, re.S):
                continue
            name = match.group("name")
            java_type = match.group("type").strip()
            schema = self._schema_for_java_type(java_type)
            schema["source"] = f"{rel}:{index + 1}"
            description = self._schema_attr(context, "description")
            example = self._schema_attr(context, "example")
            if description:
                schema["description"] = description
            if example:
                schema["example"] = self._coerce_example(example, schema.get("type"))
            fields.append(
                {
                    "name": name,
                    "schema": schema,
                    "required": bool(
                        "RequiredMode.REQUIRED" in context
                        or re.search(r"@(NotNull|NotBlank|NotEmpty)\b", context)
                    ),
                }
            )
        return fields

    def _field_annotation_context(self, lines: list[str], field_index: int) -> str:
        block = [lines[field_index]]
        for cursor in range(field_index - 1, -1, -1):
            stripped = lines[cursor].strip()
            if not stripped:
                break
            if stripped.endswith(";") or stripped.endswith("{"):
                break
            if re.search(r"\bclass\s+\w+", stripped):
                break
            block.append(lines[cursor])
        return "\n".join(reversed(block))

    def _schema_attr(self, context: str, attr_name: str) -> str | None:
        match = re.search(rf"{attr_name}\s*=\s*\"([^\"]+)\"", context, re.S)
        return match.group(1) if match else None

    def _schema_for_java_type(self, java_type: str) -> dict[str, Any]:
        simple_type = self._simple_type(java_type)
        if simple_type.startswith("List") or simple_type.startswith("Set") or java_type.endswith("[]"):
            return {"type": "array", "java_type": java_type}
        return {"type": SCALAR_JAVA_TYPES.get(simple_type, "object"), "java_type": java_type}

    def _example_from_contract(self, contract: dict[str, Any]) -> dict[str, Any]:
        example: dict[str, Any] = {}
        required = set(contract.get("required", []))
        for name, schema in contract["properties"].items():
            if "example" in schema:
                example[name] = schema["example"]
            elif name in {"page", "current", "pageNo", "pageNum"}:
                example[name] = 1
            elif name in {"limit", "size", "pageSize"}:
                example[name] = 10
            elif name in required:
                example[name] = f"{{{{{name}}}}}"
        return example

    def _coerce_example(self, value: str, schema_type: Any) -> Any:
        if schema_type == "integer" and re.fullmatch(r"-?\d+", value):
            return int(value)
        if schema_type == "number" and re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            return float(value)
        if schema_type == "boolean" and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return value

    def _resolve_java_file(
        self,
        root: Path,
        simple_type: str,
        imports: dict[str, str],
        package: str | None,
    ) -> Path | None:
        qualified_name = self._qualified_name(simple_type, imports, package)
        cache_key = (str(root), qualified_name)
        if cache_key in self._java_file_cache:
            return self._java_file_cache[cache_key]

        suffix = f"{qualified_name.replace('.', '/')}.java"
        candidates = [
            path
            for path in root.rglob(f"{simple_type}.java")
            if path.is_file() and not any(part in IGNORED_JAVA_DIRS for part in path.parts)
        ]
        exact = next((path for path in candidates if path.as_posix().endswith(suffix)), None)
        resolved = exact or (candidates[0] if candidates else None)
        self._java_file_cache[cache_key] = resolved
        return resolved

    def _imports(self, content: str) -> dict[str, str]:
        imports: dict[str, str] = {}
        for match in re.finditer(r"^\s*import\s+([\w.]+);", content, re.M):
            qualified = match.group(1)
            imports[qualified.rsplit(".", 1)[-1]] = qualified
        return imports

    def _package(self, content: str) -> str | None:
        match = re.search(r"^\s*package\s+([\w.]+);", content, re.M)
        return match.group(1) if match else None

    def _simple_type(self, java_type: str) -> str:
        simple = java_type.strip().split("<", 1)[0].rsplit(".", 1)[-1]
        return simple.rstrip("[]")

    def _qualified_name(
        self,
        simple_type: str,
        imports: dict[str, str],
        package: str | None,
    ) -> str:
        if imports.get(simple_type):
            return imports[simple_type]
        if package:
            return f"{package}.{simple_type}"
        return simple_type

    def _relative_source(self, root: Path, path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()
